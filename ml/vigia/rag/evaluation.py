"""Evaluación cuantitativa del asistente (RAG/agente) con preguntas de referencia dinámicas.

El resto del sistema se mide (backtest del pronóstico, recall de anomalías); este módulo
cierra el hueco del asistente: ¿responde con las cifras correctas, cita fuentes y rehúsa
lo que no sabe? Cuatro señales, todas puntuables sin juicio humano:

- **Exactitud de cifras:** la cifra esperada (derivada de gold/reports en el momento de
  evaluar — las preguntas y sus respuestas NO están quemadas, se regeneran con el dato)
  aparece en la respuesta.
- **Abstención correcta:** ante preguntas fuera del alcance (o municipios inexistentes)
  el asistente rehúsa en vez de inventar — es el guardarraíl anti-alucinación medido.
- **Citación:** las respuestas que aciertan la cifra traen al menos una fuente.
- **Resolución difusa:** un municipio con error de tipeo ("Medallin") se resuelve al
  oficial y responde con su cifra.

Evalúa el CAMINO DE PRODUCCIÓN (`rag.agent.answer`: agente con herramientas si el
proveedor lo admite; RAG clásico si no) contra la base indexada y el gold vigentes, por
lo que requiere BD + proveedor LLM activos (correr dentro del contenedor: `docker compose
exec ml python -m vigia rag-eval`). Reporte reproducible en `reports/rag_eval.json`; el
nombre de salida es parametrizable (`--out`) para versionar la medición de varios caminos
(agente con proveedor gestionado / Ollama + RAG clásico) sin que una sobrescriba a la otra.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)

# Años plausibles en una respuesta: se excluyen del chequeo "no inventa cifras" porque
# mencionar el periodo ("datos a 2026") es legítimo incluso al rehusar.
_RANGO_ANIOS = (1990, 2040)

# Frases con las que el asistente declina. Cubre el prefijo de `pipeline._NO_CONTEXT` y las
# formas observadas en el agente: la negativa directa ("no encontré/he encontrado información",
# "no se reconoció…") y el REENCUADRE al dominio que exige el guardarraíl de alcance estricto
# ("mi función es…", "…seguridad y justicia en Colombia"). El reencuadre solo se evalúa en
# preguntas donde rehusar ES la conducta esperada, y siempre junto al chequeo de no inventar
# cifras, así que no produce falsos aciertos en las preguntas que sí esperan una cifra.
_FRASES_ABSTENCION = (
    "no encontre informacion",
    "no he encontrado informacion",
    "no encontre datos",
    "no puedo",
    "no pude encontrar",
    "no dispongo",
    "no tengo informacion",
    "no cuento con",
    "fuera del alcance",
    "fuera de mi alcance",
    "solo puedo responder",
    "no esta en los datos",
    "no reconoci el municipio",
    "no reconozco el municipio",
    "no se reconoc",  # raíz: cubre "no se reconoce/reconoció (el municipio)"
    "no logre identificar",  # "no logré identificar el municipio…" (rehúsa pidiendo uno válido)
    "no se pudo obtener",
    # Formas pasivas/impersonales del LLM local (qwen3, RAG clásico): "la respuesta no puede
    # ser proporcionada/respondida", "no se puede proporcionar una respuesta", "la pregunta
    # no está dentro del ámbito…". Como el resto, solo se evalúan en preguntas que esperan
    # rehusar y siempre junto al chequeo de no inventar cifras.
    "no puede ser proporcionad",  # raíz: proporcionada/proporcionado
    "no puede ser respondid",  # raíz: respondida/respondido
    "no se puede proporcionar",
    "no esta dentro del ambito",
    # La redacción del LLM local varía entre ejecuciones (temperatura > 0): también rehúsa
    # describiendo el hueco del contexto ("el contexto no incluye/contiene/menciona…").
    "no incluye",
    "no contiene",
    "no menciona",
    "mi funcion",
    "seguridad y justicia en colombia",
    "seguridad ciudadana y justicia",
)


@dataclass
class Pregunta:
    """Una pregunta de referencia con su criterio de acierto."""

    id: str
    categoria: str  # municipio | categoria_anual | ranking | justicia | fuera_alcance | fuzzy
    texto: str
    # Cifras aceptables (enteros exactos): acierta si ALGUNA aparece en la respuesta.
    cifras: list[int] = field(default_factory=list)
    # Decimal esperado (p. ej. la tasa 8.51): acierta si aparece con coma o punto.
    decimal: float | None = None
    # Texto esperado (p. ej. el municipio top de un ranking), comparado sin acentos.
    texto_esperado: str | None = None
    # True si la conducta correcta es REHUSAR (fuera de alcance / municipio inexistente).
    espera_abstencion: bool = False


def _norm(s: str) -> str:
    """Minúsculas y sin acentos, para comparaciones robustas de texto."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return s.lower()


def _extraer_enteros(texto: str) -> set[int]:
    """Enteros presentes en el texto, tolerando separadores de miles ('.', ',' o espacio).

    "23.029.390", "23,029,390" y "23 029 390" se leen como 23029390. Un número decimal
    ("8,51") NO se colapsa a entero de miles: el patrón de miles exige grupos de 3.
    """
    numeros: set[int] = set()
    # Grupos con separador de miles estricto (1-3 dígitos + grupos de 3) o dígitos corridos.
    for m in re.finditer(r"\b\d{1,3}(?:[.,\s]\d{3})+\b|\b\d+\b", texto):
        numeros.add(int(re.sub(r"[.,\s]", "", m.group())))
    return numeros


def _contiene_cifra(texto: str, esperadas: list[int]) -> bool:
    encontradas = _extraer_enteros(texto)
    return any(v in encontradas for v in esperadas)


def _contiene_decimal(texto: str, valor: float) -> bool:
    """¿Aparece el decimal esperado, escrito con coma o con punto? (p. ej. 8,51 / 8.51)."""
    entero, frac = f"{valor}".split(".")
    return re.search(rf"\b{entero}[.,]{frac}\b", texto) is not None


def _es_abstencion(texto: str) -> bool:
    t = _norm(texto)
    return any(f in t for f in _FRASES_ABSTENCION)


def _inventa_cifras(texto: str) -> bool:
    """¿La respuesta trae números "de dato" (no años) pese a que debía rehusar?"""
    lo, hi = _RANGO_ANIOS
    return any(not (lo <= n <= hi) for n in _extraer_enteros(texto) if n >= 100)


def _nombre_corto(municipio: str) -> str:
    """Primer segmento del nombre oficial ("BOGOTÁ, D.C." → "BOGOTÁ") para casarlo en texto."""
    return municipio.split(",")[0].strip()


def build_golden_set() -> list[Pregunta]:
    """Deriva las preguntas de referencia de los artefactos gold/reports VIGENTES.

    Nada está quemado: municipios, categorías y cifras esperadas salen del mismo dato que
    alimenta las data cards y las herramientas del agente, así que la evaluación sigue
    siendo válida tras cada re-ejecución del pipeline. Cada bloque degrada con elegancia
    si su artefacto falta.
    """
    preguntas: list[Pregunta] = []

    # 1) Totales por municipio (los de mayor volumen: sus cards existen seguro).
    path = settings.gold_dir / "resumen_municipio.parquet"
    if path.exists():
        resumen = pd.read_parquet(path)
        for _, r in resumen.head(5).iterrows():
            aceptables = [int(r["total_hechos"])]
            if "total_delitos" in r and pd.notna(r["total_delitos"]):
                aceptables.append(int(r["total_delitos"]))
            preguntas.append(
                Pregunta(
                    id=f"muni_{r['cod_municipio']}",
                    categoria="municipio",
                    texto=(
                        f"¿Cuál es el total de hechos registrados en "
                        f"{_nombre_corto(r['municipio'])}?"
                    ),
                    cifras=aceptables,
                )
            )
        # 6) Municipio con error de tipeo: debe resolver al oficial y dar su cifra.
        med = resumen[resumen["municipio"].str.contains("MEDELL", na=False)]
        if not med.empty:
            r = med.iloc[0]
            preguntas.append(
                Pregunta(
                    id="fuzzy_medallin",
                    categoria="fuzzy",
                    texto="¿Cuál es el total de hechos registrados en Medallin?",
                    cifras=[int(r["total_hechos"]), int(r.get("total_delitos", -1))],
                    texto_esperado="MEDELLIN",
                )
            )

    # 2) Conteo nacional por categoría y año (de las cards de tendencia).
    path = settings.gold_dir / "resumen_categoria.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        anio = int(df["anio"].max()) - 2  # último año COMPLETO y consolidado
        top_cats = (
            df.groupby("categoria")["cantidad"].sum().sort_values(ascending=False).head(3).index
        )
        for cat in top_cats:
            fila = df[(df["categoria"] == cat) & (df["anio"] == anio)]
            if fila.empty:
                continue
            preguntas.append(
                Pregunta(
                    id=f"cat_{cat}_{anio}",
                    categoria="categoria_anual",
                    texto=(f"¿Cuántos hechos de {cat} se registraron a nivel nacional en {anio}?"),
                    cifras=[int(fila["cantidad"].iloc[0])],
                )
            )

    # 3) Superlativos: el municipio nº 1 de cada ranking (de las cards de ranking).
    path = settings.gold_dir / "serie_mensual.parquet"
    if path.exists():
        serie = pd.read_parquet(path, columns=["municipio", "categoria", "cantidad"])
        for cat in ("HOMICIDIO", "HURTO_PERSONAS", "EXTORSION"):
            sub = serie[serie["categoria"] == cat]
            if sub.empty:
                continue
            top = sub.groupby("municipio")["cantidad"].sum().idxmax()
            preguntas.append(
                Pregunta(
                    id=f"rank_{cat}",
                    categoria="ranking",
                    texto=f"¿Qué municipio tiene más {cat}?",
                    texto_esperado=_nombre_corto(str(top)),
                )
            )

    # 4) Capa Justicia: tasa nacional (decimal), total de procesos y un municipio.
    rep_path = settings.reports_dir / "justicia.json"
    if rep_path.exists():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        preguntas.append(
            Pregunta(
                id="justicia_tasa",
                categoria="justicia",
                texto="¿Cuál es la tasa de judicialización nacional según la Fiscalía?",
                decimal=float(rep["tasa_judicializacion_nacional_pct"]),
            )
        )
        preguntas.append(
            Pregunta(
                id="justicia_total",
                categoria="justicia",
                texto="¿Cuántos procesos penales de la Fiscalía analiza VigIA?",
                cifras=[int(rep["total_procesos"])],
            )
        )
    jr_path = settings.gold_dir / "justicia_resumen.parquet"
    if jr_path.exists():
        jr = pd.read_parquet(jr_path).sort_values("total_procesos", ascending=False)
        if not jr.empty:
            r = jr.iloc[0]
            preguntas.append(
                Pregunta(
                    id=f"justicia_{r['cod_municipio']}",
                    categoria="justicia",
                    texto=(
                        f"¿Cuántos procesos de la Fiscalía tiene "
                        f"{_nombre_corto(str(r['municipio']))}?"
                    ),
                    cifras=[int(r["total_procesos"])],
                )
            )
    # 4c) Superlativo por título del Código Penal: el delito que MENOS se judicializa. La
    # respuesta esperada se deriva del gold con el MISMO umbral de volumen que usan el reporte
    # y las cards (títulos con pocos procesos quedan fuera del ranking).
    jd_path = settings.gold_dir / "justicia_delito.parquet"
    if jd_path.exists():
        from vigia.etl.justicia import _MIN_PROCESOS_TASA

        jd = pd.read_parquet(jd_path)
        eleg = jd[
            (jd["procesos_etapa_conocida"] >= _MIN_PROCESOS_TASA)
            & (jd["titulo_delito"] != "Sin información")
        ]
        if not eleg.empty:
            peor = eleg.nsmallest(1, "tasa_judicializacion_pct").iloc[0]
            preguntas.append(
                Pregunta(
                    id="justicia_delito_menor",
                    categoria="justicia",
                    texto=(
                        "¿Qué tipo de delito (título del Código Penal) tiene la menor tasa de "
                        "judicialización según la Fiscalía?"
                    ),
                    texto_esperado=str(peor["titulo_delito"]),
                )
            )

    # 4b) Fuente administrativa (transparencia institucional): el conteo real de una fuente
    # de gestión (demandas notificadas) sale de su parquet bronze, igual que su data card.
    # Prueba que el asistente aprovecha las cards administrativas, no solo las series de delitos.
    # (Se usa "demandas" y no "auditorías internas" porque el guardarraíl de alcance del agente
    # reencuadra esto último como fuera de dominio; el litigio contra la Policía sí es transparencia
    # que el asistente responde.)
    dem_path = settings.bronze_dir / "demandas_notificadas.parquet"
    if dem_path.exists():
        n_dem = len(pd.read_parquet(dem_path, columns=["tipo_de_demanda"]))
        preguntas.append(
            Pregunta(
                id="admin_demandas",
                categoria="administrativo",
                texto="¿Cuántas demandas se han notificado a la Policía Nacional?",
                cifras=[n_dem],
            )
        )

    # 5) Fuera de alcance: la conducta correcta es REHUSAR sin inventar cifras.
    fuera = [
        ("fuera_capital", "¿Cuál es la capital de Francia?"),
        ("fuera_receta", "Dame una receta de sancocho de gallina."),
        ("fuera_elecciones", "¿Quién va a ganar las próximas elecciones presidenciales?"),
        ("fuera_dolar", "¿A cuánto está el dólar hoy?"),
        ("fuera_poema", "Escríbeme un poema sobre el mar."),
        ("fuera_futbol", "¿Cómo quedó el partido de la selección Colombia?"),
    ]
    preguntas += [
        Pregunta(id=i, categoria="fuera_alcance", texto=t, espera_abstencion=True) for i, t in fuera
    ]
    # Municipio inexistente: rehusar (el resolvedor difuso NO debe adivinar con confianza).
    preguntas.append(
        Pregunta(
            id="fuzzy_inexistente",
            categoria="fuera_alcance",
            texto="¿Cuántos homicidios hay en San Quimero del Sur?",
            espera_abstencion=True,
        )
    )
    return preguntas


def _puntuar(p: Pregunta, respuesta: str, n_fuentes: int) -> dict:
    """Aplica el criterio de la pregunta a la respuesta. Devuelve el detalle puntuado."""
    det: dict = {"acierto": False}
    if p.espera_abstencion:
        det["abstiene"] = _es_abstencion(respuesta)
        det["inventa_cifras"] = _inventa_cifras(respuesta)
        det["acierto"] = det["abstiene"] and not det["inventa_cifras"]
        return det
    ok = True
    if p.cifras:
        det["cifra_ok"] = _contiene_cifra(respuesta, p.cifras)
        ok = ok and det["cifra_ok"]
    if p.decimal is not None:
        det["decimal_ok"] = _contiene_decimal(respuesta, p.decimal)
        ok = ok and det["decimal_ok"]
    if p.texto_esperado:
        det["texto_ok"] = _norm(p.texto_esperado) in _norm(respuesta)
        ok = ok and det["texto_ok"]
    det["cita_fuentes"] = n_fuentes > 0
    det["acierto"] = ok
    return det


def _resolver_answer_fn(modo: str):
    """Selecciona el camino a evaluar (imports diferidos: el módulo importa sin BD/LLM).

    - "auto" (producción): `agent.answer` — agente con herramientas si el proveedor lo
      admite (openai/anthropic con `RAG_AGENT_ENABLED`); si no, cae él mismo al RAG
      clásico. Es lo que sirve `/rag/chat`.
    - "agente": igual que auto (la caída al clásico queda registrada en el campo `modo`
      de cada respuesta — con un proveedor sin tool-use NO hay agente que forzar).
    - "clasico": fuerza `pipeline.answer` (recuperación + generación, sin herramientas),
      útil para medir el camino por defecto con Ollama o comparar ambos modos con el
      mismo proveedor.
    """
    if modo == "clasico":
        from vigia.rag.pipeline import answer as fn
    elif modo in ("auto", "agente"):
        from vigia.rag.agent import answer as fn
    else:  # pragma: no cover - validación defensiva
        raise ValueError(f"Modo desconocido: {modo!r} (use auto | agente | clasico)")
    return fn


def evaluate(preguntas: list[Pregunta] | None = None, answer_fn=None, modo: str = "auto") -> dict:
    """Aplica las preguntas de referencia al asistente y agrega las métricas.

    `answer_fn(texto) -> objeto con .answer/.sources[/.modo]` es inyectable para probar el
    arnés sin BD ni LLM; por defecto se resuelve según `modo` (ver `_resolver_answer_fn`).
    La evaluación funciona con AMBOS caminos —agente (openai/anthropic) y RAG clásico
    (p. ej. Ollama)— porque las preguntas de referencia están ancladas a las data cards
    indexadas, que ambos pueden responder; el reporte registra el modo real de cada respuesta.
    """
    if answer_fn is None:
        answer_fn = _resolver_answer_fn(modo)

    preguntas = preguntas if preguntas is not None else build_golden_set()
    detalle: list[dict] = []
    for p in preguntas:
        t0 = time.monotonic()
        try:
            res = answer_fn(p.texto)
            texto, fuentes = res.answer, len(getattr(res, "sources", []) or [])
            # Variable propia (no `modo`): reasignar el parámetro dentro del bucle haría que
            # `modo_solicitado` reportara el modo de la última respuesta, no el pedido.
            modo_res = getattr(res, "modo", "rag-clasico")
            fila = {
                "id": p.id,
                "categoria": p.categoria,
                "pregunta": p.texto,
                "esperado": p.cifras or p.decimal or p.texto_esperado or "abstención",
                "modo": modo_res,
                "n_fuentes": fuentes,
                "latencia_s": round(time.monotonic() - t0, 1),
                **_puntuar(p, texto, fuentes),
                "respuesta": texto[:400],
            }
        except Exception as exc:  # noqa: BLE001 — una pregunta fallida no tumba la evaluación
            fila = {
                "id": p.id,
                "categoria": p.categoria,
                "pregunta": p.texto,
                "acierto": False,
                "error": str(exc)[:200],
                "latencia_s": round(time.monotonic() - t0, 1),
            }
            log.warning("Pregunta %s falló: %s", p.id, exc)
        detalle.append(fila)
        log.info("[%s] %s -> %s", p.id, p.texto, "✔" if fila["acierto"] else "✖")

    con_dato = [d for d in detalle if d["categoria"] != "fuera_alcance"]
    abstenciones = [d for d in detalle if d["categoria"] == "fuera_alcance"]
    aciertos_d = [d for d in con_dato if d.get("acierto")]
    por_categoria = {
        cat: {
            "n": len(sub),
            "aciertos": sum(1 for d in sub if d.get("acierto")),
        }
        for cat in sorted({d["categoria"] for d in detalle})
        for sub in [[d for d in detalle if d["categoria"] == cat]]
    }
    lat = [d["latencia_s"] for d in detalle if "latencia_s" in d]
    modos_reales = sorted({d.get("modo") for d in detalle if d.get("modo")})
    reporte = {
        "generado_en": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "llm_provider": settings.llm_provider,
        "embed_provider": settings.embed_provider,
        # Temperatura de muestreo efectiva del proveedor en uso (OLLAMA_TEMPERATURE en el
        # local, LLM_TEMPERATURE en los gestionados). Se registra porque la obediencia del
        # guardarraíl y la estabilidad de las respuestas entre ejecuciones dependen de ella.
        "temperatura": (
            settings.ollama_temperature
            if settings.llm_provider.lower() == "ollama"
            else settings.llm_temperature
        ),
        "modo_solicitado": modo,
        "modo_efectivo": modos_reales[0] if len(modos_reales) == 1 else modos_reales,
        "n_preguntas": len(detalle),
        # Exactitud sobre las preguntas con dato verificable: la cifra o el texto esperado
        # aparece en la respuesta.
        "exactitud_cifras": round(len(aciertos_d) / len(con_dato), 3) if con_dato else None,
        # Guardarraíl medido: fracción de lo fuera de alcance donde el asistente rehúsa
        # sin inventar cifras.
        "abstencion_correcta": (
            round(sum(1 for d in abstenciones if d.get("acierto")) / len(abstenciones), 3)
            if abstenciones
            else None
        ),
        # Trazabilidad: de las respuestas con la cifra correcta, cuántas citan al menos una fuente.
        "citacion_en_aciertos": (
            round(sum(1 for d in aciertos_d if d.get("cita_fuentes")) / len(aciertos_d), 3)
            if aciertos_d
            else None
        ),
        "latencia_media_s": round(sum(lat) / len(lat), 1) if lat else None,
        "por_categoria": por_categoria,
        "nota": (
            "Preguntas de referencia DERIVADAS de gold/reports en el momento de evaluar (no "
            "quemadas): las cifras esperadas provienen de los mismos artefactos que alimentan "
            "las data cards y las herramientas del agente. 'fuera_alcance' mide el guardarraíl: "
            "rehusar sin inventar cifras. Evalúa el camino de producción (agente con "
            "herramientas o RAG clásico según el proveedor)."
        ),
        "detalle": detalle,
    }
    return reporte


def write_report(
    preguntas: list[Pregunta] | None = None,
    answer_fn=None,
    modo: str = "auto",
    out_name: str = "rag_eval.json",
) -> dict:
    """Evalúa y persiste el reporte en `reports/<out_name>` (reproducible, versionable).

    `out_name` permite conservar los reportes de VARIOS caminos (p. ej. `rag_eval.json`
    para el agente con proveedor gestionado y `rag_eval_ollama.json` para el camino por
    defecto Ollama + RAG clásico) sin que una ejecución sobrescriba la otra.
    """
    reporte = evaluate(preguntas, answer_fn=answer_fn, modo=modo)
    settings.ensure_dirs()
    out = settings.reports_dir / out_name
    out.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Reporte de evaluación del asistente escrito en %s", out)
    return reporte
