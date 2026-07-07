"""Registro de herramientas del agente RAG.

El asistente de VigIA puede actuar como un **agente**: en vez de un enrutador por
palabras clave (`hybrid.py`), el LLM **decide** qué herramienta invocar (pronóstico,
anomalías, embudo de judicialización, serie histórica o búsqueda en la base de
conocimiento), observa el resultado real y sintetiza la respuesta. Todas las cifras
provienen de estas herramientas —datos abiertos oficiales— y NUNCA del LLM: es el mismo
guardarraíl anti-alucinación del RAG clásico, llevado al agente.

El registro es **declarativo y genérico**: cada herramienta expone un esquema JSON y un
ejecutor que **reúsa el código de producción** (`forecasting.predict`, `anomaly`, las
tablas gold y la recuperación de `pipeline.retrieve`). Añadir una herramienta = añadir
una entrada a `TOOLS`, sin tocar el bucle del agente (`agent.py`) ni los proveedores
(`providers.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from vigia.config import settings
from vigia.logging import get_logger
from vigia.rag.hybrid import _norm, match_categoria, match_municipio

log = get_logger(__name__)


@dataclass(frozen=True)
class Tool:
    """Una herramienta invocable por el agente.

    `parameters` es un JSON Schema de objeto (el contrato que el LLM rellena); `run`
    recibe esos argumentos por nombre y devuelve un dict JSON-serializable. `run`
    NUNCA debe lanzar: degrada devolviendo `{"error": ...}` o `{"encontrado": False}`.
    """

    name: str
    description: str
    parameters: dict
    run: Callable[..., dict]


# ───────────── Carga perezosa de gold (con invalidación por mtime) ─────────────
# Las herramientas leen las tablas gold. La serie mensual (~3 millones de filas) se cachea
# y se invalida por la marca de tiempo del parquet, igual que el caché del API (`api/main.py`),
# para que un re-pipeline se refleje sin reiniciar el proceso.
_cache: dict[str, dict] = {}


def _load_gold(name: str) -> pd.DataFrame | None:
    path = settings.gold_dir / f"{name}.parquet"
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    entry = _cache.get(name)
    if entry is None or entry["mtime"] != mtime:
        _cache[name] = {"mtime": mtime, "df": pd.read_parquet(path)}
    return _cache[name]["df"]


def _resolver_categoria(texto: str, disponibles: list[str]) -> str | None:
    """Casa un texto libre de categoría contra las categorías REALES de un municipio.

    Conservador: exacto normalizado → subcadena → palabras clave (`match_categoria`).
    Devuelve None si no hay coincidencia clara (el ejecutor responde con la lista
    disponible en vez de asumir una categoría arbitraria — evita un pronóstico
    confiado sobre el delito equivocado).
    """
    if not disponibles:
        return None
    t = _norm(texto)
    norm_map = {_norm(c): c for c in disponibles}
    if t in norm_map:
        return norm_map[t]
    for cn, original in norm_map.items():
        if t and (t in cn or cn in t):
            return original
    return match_categoria(texto, disponibles)


def _periodo_str(value: object) -> str:
    """Normaliza un periodo (Timestamp/fecha/str) a 'YYYY-MM' para una salida estable."""
    try:
        return pd.Timestamp(value).strftime("%Y-%m")
    except (ValueError, TypeError):
        return str(value)[:7]


# ───────────────────────── Ejecutores (reúsan producción) ─────────────────────────
def _run_resolver_municipio(texto: str) -> dict:
    resumen = _load_gold("resumen_municipio")
    if resumen is None:
        return {"error": "Datos no disponibles. Ejecuta el pipeline ETL."}
    muni = match_municipio(texto, resumen[["cod_municipio", "municipio", "departamento"]])
    if muni is None:
        return {"encontrado": False, "nota": "No se reconoció un municipio en el texto."}
    serie = _load_gold("serie_mensual")
    categorias: list[str] = []
    if serie is not None:
        sub = serie[serie["cod_municipio"] == muni["cod_municipio"]]
        categorias = sorted(sub["categoria"].unique().tolist())
    return {"encontrado": True, **muni, "categorias_disponibles": categorias}


def _run_pronostico(cod_municipio: str, categoria: str, horizonte: int = 6) -> dict:
    serie = _load_gold("serie_mensual")
    if serie is None:
        return {"error": "Datos no disponibles. Ejecuta el pipeline ETL."}
    cod = str(cod_municipio)
    sub = serie[serie["cod_municipio"] == cod]
    if sub.empty:
        return {"encontrado": False, "nota": f"Sin historia para el municipio {cod}."}
    disponibles = sorted(sub["categoria"].unique().tolist())
    cat = _resolver_categoria(categoria, disponibles)
    if cat is None:
        return {
            "encontrado": False,
            "nota": "No se reconoció la categoría. Elige una de las disponibles.",
            "categorias_disponibles": disponibles,
        }
    from vigia.ml.forecasting import predict

    try:
        horizonte = max(1, min(int(horizonte), 12))
        pts = predict(serie, cod, cat, horizon=horizonte)
    except RuntimeError as exc:  # modelo ausente o ilegible → 503 accionable aguas arriba
        return {"error": str(exc)}
    if not pts:
        return {"encontrado": False, "nota": "Sin pronóstico disponible para esa serie."}
    proyeccion = [
        {
            "periodo": _periodo_str(p.get("periodo")),
            "prediccion": p.get("prediccion"),
            "limite_inferior": p.get("limite_inferior"),
            "limite_superior": p.get("limite_superior"),
        }
        for p in pts
    ]
    return {
        "encontrado": True,
        "cod_municipio": cod,
        "categoria": cat,
        "horizonte": horizonte,
        "banda_pct": 80,
        "nota": "Proyección estadística (ayuda a la decisión), no una certeza.",
        "proyeccion": proyeccion,
    }


def _run_serie_historica(cod_municipio: str, categoria: str, meses: int = 12) -> dict:
    serie = _load_gold("serie_mensual")
    if serie is None:
        return {"error": "Datos no disponibles. Ejecuta el pipeline ETL."}
    cod = str(cod_municipio)
    sub = serie[serie["cod_municipio"] == cod]
    if sub.empty:
        return {"encontrado": False, "nota": f"Sin historia para el municipio {cod}."}
    cat = _resolver_categoria(categoria, sorted(sub["categoria"].unique().tolist()))
    if cat is None:
        return {
            "encontrado": False,
            "nota": "No se reconoció la categoría.",
            "categorias_disponibles": sorted(sub["categoria"].unique().tolist()),
        }
    sc = sub[sub["categoria"] == cat].sort_values("periodo")
    meses = max(1, min(int(meses), 60))
    cola = sc.tail(meses)
    puntos = [
        {"periodo": _periodo_str(r["periodo"]), "cantidad": int(r["cantidad"])}
        for _, r in cola.iterrows()
    ]
    return {
        "encontrado": True,
        "cod_municipio": cod,
        "categoria": cat,
        "total_periodo": int(cola["cantidad"].sum()),
        "serie": puntos,
    }


def _run_anomalias(cod_municipio: str) -> dict:
    an = _load_gold("anomalias")
    if an is None:
        return {"encontrado": False, "nota": "No hay anomalías calculadas. Ejecuta el pipeline."}
    cod = str(cod_municipio)
    sub = an[an["cod_municipio"] == cod].copy()
    if sub.empty:
        return {"encontrado": True, "cod_municipio": cod, "n_anomalias": 0, "anomalias": []}
    sub = sub.sort_values("periodo", ascending=False)
    items = [
        {
            "categoria": r["categoria"],
            "periodo": _periodo_str(r["periodo"]),
            "cantidad": int(r["cantidad"]),
            "severidad": r["severidad"],
            "score_z": round(float(r["score_z"]), 2),
        }
        for _, r in sub.head(20).iterrows()
    ]
    return {
        "encontrado": True,
        "cod_municipio": cod,
        "n_anomalias": int(len(sub)),
        "anomalias": items,
    }


def _run_embudo_justicia(cod_municipio: str) -> dict:
    jr = _load_gold("justicia_resumen")
    if jr is None:
        return {"encontrado": False, "nota": "Capa de Justicia no disponible. Ejecuta el pipeline."}
    cod = str(cod_municipio)
    row = jr[jr["cod_municipio"] == cod]
    if row.empty:
        return {"encontrado": False, "nota": f"Sin datos de judicialización para {cod}."}
    r = row.iloc[0]
    return {
        "encontrado": True,
        "cod_municipio": cod,
        "municipio": r["municipio"],
        "total_procesos": int(r["total_procesos"]),
        "n_judicializados": int(r["n_judicializados"]),
        "tasa_judicializacion_pct": round(float(r["tasa_judicializacion_pct"]), 2),
        "nota": "Tasa = procesos que superan la indagación / total con etapa conocida.",
    }


def _run_buscar_conocimiento(consulta: str) -> dict:
    from vigia.rag.pipeline import MIN_SCORE, retrieve

    chunks = retrieve(consulta)
    relevantes = [c for c in chunks if c.get("score", 0.0) >= MIN_SCORE]
    if not relevantes:
        return {
            "encontrado": False,
            "nota": "Sin fragmentos relevantes en la base de conocimiento.",
        }
    return {
        "encontrado": True,
        "fragmentos": [
            {"contenido": c["content"], "score": c.get("score"), "fuente": c.get("metadata", {})}
            for c in relevantes
        ],
    }


# ───────────────────────── Registro declarativo ─────────────────────────
def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


TOOLS: list[Tool] = [
    Tool(
        name="resolver_municipio",
        description=(
            "Convierte el nombre de un municipio escrito por el ciudadano (p. ej. 'Cali', "
            "'Medellin', 'Bogota') en su código DANE oficial y lista las categorías de delito "
            "disponibles para él. Úsala SIEMPRE primero cuando la pregunta mencione un lugar, "
            "porque las demás herramientas necesitan el código del municipio."
        ),
        parameters=_obj(
            {"texto": {"type": "string", "description": "Nombre del municipio mencionado."}},
            ["texto"],
        ),
        run=_run_resolver_municipio,
    ),
    Tool(
        name="pronostico",
        description=(
            "Pronóstico del modelo VigIA para un delito en un municipio: proyección mensual con "
            "banda de incertidumbre (~80%). Úsala para preguntas sobre el FUTURO o la tendencia "
            "esperada. Requiere el código DANE del municipio (de 'resolver_municipio')."
        ),
        parameters=_obj(
            {
                "cod_municipio": {"type": "string", "description": "Código DANE del municipio."},
                "categoria": {
                    "type": "string",
                    "description": "Categoría de delito (p. ej. HOMICIDIO, HURTO).",
                },
                "horizonte": {
                    "type": "integer",
                    "description": "Meses a proyectar (1-12, def. 6).",
                },
            },
            ["cod_municipio", "categoria"],
        ),
        run=_run_pronostico,
    ),
    Tool(
        name="serie_historica",
        description=(
            "Cifras históricas registradas de un delito en un municipio (últimos N meses). Úsala "
            "para el PASADO o el presente ('cuántos hubo', 'cómo ha evolucionado'). Requiere el "
            "código DANE del municipio."
        ),
        parameters=_obj(
            {
                "cod_municipio": {"type": "string", "description": "Código DANE del municipio."},
                "categoria": {"type": "string", "description": "Categoría de delito."},
                "meses": {
                    "type": "integer",
                    "description": "Cuántos meses recientes (1-60, def. 12).",
                },
            },
            ["cod_municipio", "categoria"],
        ),
        run=_run_serie_historica,
    ),
    Tool(
        name="anomalias",
        description=(
            "Anomalías (picos atípicos al alza = alertas tempranas) detectadas para un municipio, "
            "por categoría y mes. Úsala para 'alertas', 'repuntes' o 'meses atípicos'. Requiere el "
            "código DANE del municipio."
        ),
        parameters=_obj(
            {"cod_municipio": {"type": "string", "description": "Código DANE del municipio."}},
            ["cod_municipio"],
        ),
        run=_run_anomalias,
    ),
    Tool(
        name="embudo_justicia",
        description=(
            "Tasa de judicialización (eje Justicia, Fiscalía) de un municipio: qué fracción de los "
            "procesos supera la indagación. Úsala para preguntas sobre justicia, judicialización o "
            "impunidad. Requiere el código DANE del municipio."
        ),
        parameters=_obj(
            {"cod_municipio": {"type": "string", "description": "Código DANE del municipio."}},
            ["cod_municipio"],
        ),
        run=_run_embudo_justicia,
    ),
    Tool(
        name="buscar_conocimiento",
        description=(
            "Búsqueda semántica en la base de conocimiento (resúmenes de datos oficiales y "
            "documentos de política pública). Úsala para definiciones, contexto, marco normativo o "
            "cuando la pregunta NO encaje con las demás herramientas."
        ),
        parameters=_obj(
            {"consulta": {"type": "string", "description": "La consulta en lenguaje natural."}},
            ["consulta"],
        ),
        run=_run_buscar_conocimiento,
    ),
]

_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}


def execute(name: str, arguments: dict) -> dict:
    """Ejecuta una herramienta por nombre de forma defensiva (nunca lanza al bucle del agente)."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return {"error": f"Herramienta desconocida: {name}"}
    try:
        return tool.run(**(arguments or {}))
    except TypeError as exc:  # argumentos inválidos enviados por el LLM
        return {"error": f"Argumentos inválidos para {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001 — degradación elegante, el agente sigue
        log.warning("Herramienta %s falló: %s", name, exc)
        return {"error": f"La herramienta {name} no pudo completarse: {exc}"}


def anthropic_schemas() -> list[dict]:
    """Esquemas en el formato de tool-use de Anthropic."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in TOOLS
    ]


def openai_schemas() -> list[dict]:
    """Esquemas en el formato de function-calling de OpenAI."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in TOOLS
    ]
