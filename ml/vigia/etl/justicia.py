"""Capa "Justicia" — gold de los procesos de la Fiscalía (independiente de la Policía).

Toma el agregado de bronze (`justicia_procesos.parquet`, ya agrupado por municipio × año ×
etapa × título penal: ese parquet lo produce la ingesta por streaming keyset + conteo local,
porque la agregación server-side de la Fiscalía no es viable — ver
`soda.fetch_streamed_aggregate`) y produce:

- `gold/justicia_anual.parquet`: serie de procesos por `municipio × año × etapa`.
- `gold/justicia_resumen.parquet`: por municipio, total de procesos y **tasa de judicialización**
  (fracción que supera la indagación → embudo Indagación → Investigación → Juicio → Ejecución).
- `gold/justicia_delito.parquet`: resumen NACIONAL por **título del Código Penal** (total,
  judicializados y tasa por título) — responde "¿qué delito se judicializa menos?". Si el bronze
  es anterior (sin la columna `titulo_delito`), esta salida se omite y el resto no cambia.
- `reports/justicia.json`: embudo nacional (por clase Y por etapa cruda de la cadena penal),
  tasa de judicialización (nacional, por título del Código Penal y por año del hecho), cobertura
  y el bloque `procedencia` (conciliación bronze → gold con los descartes por causa, más el
  linaje de la ingesta por streaming si el meta del bronze lo trae). Reproducible.

NO se fusiona con la serie de delitos de la Policía (silver): una *noticia criminal/proceso* no es
un *hecho registrado* por la Policía; mezclarlas sería doble conteo. Es una capa PARALELA cuyo
aporte diferencial es la dimensión de Justicia (`etapa`), ausente en cualquier conteo de delitos.

**Grano municipio × año × etapa (no mensual):** el valor diferencial —el embudo de judicialización—
no necesita el mes. El año va en el grupo (la ingesta agrega localmente, ver `datasets.py`). El
detalle mensual queda como mejora futura: solo añadiría una columna al `group_cols` del streaming.

**Advertencias de uso (documentadas también en docs/):**
- (1) **rezago judicial** — un proceso por un hecho reciente puede seguir en indagación o sin
  radicar, así que los años recientes quedan subestimados;
- (2) la **indagación domina** (la mayoría de noticias no avanza), por eso el valor está en la
  *tasa*, no en el volumen bruto;
- (3) la taxonomía penal de la Fiscalía (títulos del Código Penal) no es 1:1 con las categorías
  de la Policía — por eso el desglose por delito usa la taxonomía PROPIA de la fuente, sin
  cruces forzados;
- (4) el ranking de tasas por título solo **compara títulos con volumen suficiente**
  (`_MIN_PROCESOS_TASA`): con pocos procesos una tasa extrema es ruido, no señal;
- (5) toda tasa **agregada** (nacional, municipal, por título) **mezcla cohortes de hechos
  2004-2026**: un proceso reciente aún puede avanzar de etapa, así que sirve para comparar
  territorios o delitos entre sí, no años recientes contra antiguos — el bloque
  `tasa_por_anio` del reporte muestra ese efecto con el dato.
"""

from __future__ import annotations

import json
import unicodedata

import pandas as pd

from vigia.config import settings
from vigia.etl.silver import _to_dane5
from vigia.logging import get_logger

log = get_logger(__name__)

# Etapas que SUPERAN la indagación (el proceso avanzó en la cadena de justicia). Se comparan sobre
# una forma normalizada (minúsculas, sin tildes) para tolerar variaciones de escritura de la fuente.
_ADVANCED_KEYS = ("investigaci", "juicio", "ejecuci")  # Investigación, Juicio, Ejecución de Penas
_INDAGACION_KEY = "indagaci"

# Volumen mínimo de procesos con etapa conocida para que un título del Código Penal entre al
# RANKING de tasas de judicialización (la tabla completa conserva todos los títulos): con pocos
# procesos una tasa extrema es ruido estadístico, no señal. La pregunta de referencia del
# asistente (`rag/evaluation.py`) usa este mismo umbral para derivar su respuesta esperada.
_MIN_PROCESOS_TASA = 10_000


def _norm(s: str) -> str:
    """minúsculas + sin tildes, para clasificar la etapa de forma robusta."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn"
    ).lower()


def _orden_etapa(etapa: str) -> int:
    """Posición de la etapa en la cadena penal (Indagación → Investigación → Juicio →
    Ejecución), para presentar el embudo como secuencia — mismo orden que la pestaña Justicia
    del tablero. Etapas no reconocidas van al final."""
    n = _norm(etapa)
    cadena = (_INDAGACION_KEY, *_ADVANCED_KEYS)
    return next((i for i, k in enumerate(cadena) if k in n), len(cadena))


def _clasifica_etapa(etapa: pd.Series) -> pd.Series:
    """Clasifica cada etapa en 'judicializado' | 'indagacion' | 'desconocido'."""
    norm = etapa.map(_norm)
    es_avanzada = norm.apply(lambda n: any(k in n for k in _ADVANCED_KEYS))
    es_indag = norm.str.contains(_INDAGACION_KEY, na=False)
    return pd.Series(
        [
            "judicializado" if a else "indagacion" if i else "desconocido"
            for a, i in zip(es_avanzada, es_indag, strict=True)
        ],
        index=etapa.index,
    )


def _official_names(df: pd.DataFrame) -> pd.DataFrame:
    """Asigna municipio/departamento oficiales (DIVIPOLA) por código DANE; degrada si falta."""
    from vigia.etl.divipola import load_municipios

    try:
        ref = load_municipios()[["cod_municipio", "municipio", "departamento", "cod_departamento"]]
    except RuntimeError as exc:
        log.warning("Nombres oficiales no aplicados a Justicia (%s)", exc)
        df["municipio"] = pd.NA
        df["departamento"] = pd.NA
        df["cod_departamento"] = df["cod_municipio"].str.slice(0, 2)
        return df
    return df.merge(ref, on="cod_municipio", how="left")


def build_justicia() -> pd.DataFrame:
    """Construye las tablas gold de la capa Justicia y el reporte. Devuelve `justicia_anual`."""
    src = settings.bronze_dir / "justicia_procesos.parquet"
    if not src.exists():
        raise RuntimeError(
            "No hay bronze de Justicia. Ejecute `vigia ingest --only justicia_procesos`."
        )
    raw = pd.read_parquet(src)
    log.info("Justicia (Fiscalía): %d filas agregadas leídas de la capa bronze", len(raw))

    df = pd.DataFrame(index=raw.index)
    df["cod_municipio"] = _to_dane5(raw["cod_dane_hecho"], "A")
    df["anio"] = pd.to_numeric(raw["a_o_hecho"], errors="coerce")
    df["etapa"] = raw["etapa"].astype("string").str.strip()
    df["n_procesos"] = pd.to_numeric(raw["n_procesos"], errors="coerce").fillna(0).astype("int64")
    # Título del Código Penal (dimensión penal). Un bronze anterior no la trae: se degrada con
    # elegancia (sin salida por delito, el resto idéntico).
    con_delito = "titulo_delito" in raw.columns
    if con_delito:
        titulo = raw["titulo_delito"].astype("string").str.strip()
        df["titulo_delito"] = titulo.where(titulo.notna() & (titulo != ""), "Sin información")

    # Descarta filas sin municipio/año válidos o fuera de rango (incluye 'Sin Información'),
    # DEJANDO RASTRO: el bloque `procedencia` del reporte concilia bronze → gold y desglosa
    # los procesos descartados por causa (atribución excluyente, en este orden).
    sin_municipio = df["cod_municipio"].isna()
    anio_invalido = ~sin_municipio & ~df["anio"].between(2003, 2026)
    conteo_no_positivo = ~sin_municipio & ~anio_invalido & ~(df["n_procesos"] > 0)
    procedencia = _procedencia(df, sin_municipio, anio_invalido, conteo_no_positivo)
    df = df[~(sin_municipio | anio_invalido | conteo_no_positivo)].copy()
    df["anio"] = df["anio"].astype("int64")
    df["clase_etapa"] = _clasifica_etapa(df["etapa"])

    # Re-agrega por si el DANE de 8→5 colapsó centros poblados al mismo municipio.
    anual = df.groupby(["cod_municipio", "anio", "etapa", "clase_etapa"], as_index=False)[
        "n_procesos"
    ].sum()
    anual = _official_names(anual)

    # Resumen por municipio + tasa de judicialización (sobre etapas CONOCIDAS).
    resumen = (
        anual.groupby("cod_municipio")
        .agg(
            municipio=("municipio", "first"),
            departamento=("departamento", "first"),
            total_procesos=("n_procesos", "sum"),
        )
        .reset_index()
    )
    judic = (
        anual[anual["clase_etapa"] == "judicializado"].groupby("cod_municipio")["n_procesos"].sum()
    )
    conoc = (
        anual[anual["clase_etapa"] != "desconocido"].groupby("cod_municipio")["n_procesos"].sum()
    )
    resumen["n_judicializados"] = resumen["cod_municipio"].map(judic).fillna(0).astype("int64")
    resumen["procesos_etapa_conocida"] = (
        resumen["cod_municipio"].map(conoc).fillna(0).astype("int64")
    )
    resumen["tasa_judicializacion_pct"] = (
        100 * resumen["n_judicializados"] / resumen["procesos_etapa_conocida"].clip(lower=1)
    ).round(2)

    # Resumen NACIONAL por título del Código Penal (¿qué delito se judicializa menos?).
    delito = _resumen_delito(df) if con_delito else None

    settings.ensure_dirs()
    anual.to_parquet(settings.gold_dir / "justicia_anual.parquet", index=False)
    resumen.to_parquet(settings.gold_dir / "justicia_resumen.parquet", index=False)
    delito_path = settings.gold_dir / "justicia_delito.parquet"
    if delito is not None:
        delito.to_parquet(delito_path, index=False)
    elif delito_path.exists():
        # Evita dejar un gold por delito de una ejecución anterior que ya no calza con el bronze.
        delito_path.unlink()
        log.warning(
            "Bronze sin 'titulo_delito': se retiró el gold por delito anterior "
            "(vuelva a descargar justicia_procesos para regenerarlo)."
        )
    _write_report(anual, resumen, delito, procedencia)
    log.info(
        "Justicia (Fiscalía) escrita en la capa gold: %d filas anuales, %d municipios, %s",
        len(anual),
        resumen["cod_municipio"].nunique(),
        f"{len(delito)} títulos penales" if delito is not None else "sin desglose por delito",
    )
    return anual


def _procedencia(
    df: pd.DataFrame,
    sin_municipio: pd.Series,
    anio_invalido: pd.Series,
    conteo_no_positivo: pd.Series,
) -> dict:
    """Conciliación bronze → gold para el reporte: totales y descartes por causa.

    Cada fila de ORIGEN de la Fiscalía cuenta exactamente 1 en el agregado del bronze, así
    que `procesos_bronze` equivale a las filas leídas por el streaming; si el meta del bronze
    trae el linaje de la ingesta (`source_rows`, `source_count` — metas anteriores no lo
    traen), se adjunta para cerrar la conciliación contra el `count(1)` del servidor.
    """
    total = int(df["n_procesos"].sum())
    descartes = {
        "sin_municipio_valido": int(df.loc[sin_municipio, "n_procesos"].sum()),
        "anio_invalido_o_fuera_de_rango": int(df.loc[anio_invalido, "n_procesos"].sum()),
        "conteo_no_positivo": int(df.loc[conteo_no_positivo, "n_procesos"].sum()),
    }
    n_descartados = sum(descartes.values())
    out = {
        "filas_agregadas_bronze": int(len(df)),
        "procesos_bronze": total,
        "procesos_gold": total - n_descartados,
        "procesos_descartados": descartes,
        "descartados_pct": round(100 * n_descartados / max(total, 1), 2),
    }
    meta_path = settings.bronze_dir / "justicia_procesos.meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("source_rows") is not None or meta.get("source_count") is not None:
            out["conciliacion_ingesta"] = {
                "filas_origen_leidas": meta.get("source_rows"),
                "count_servidor": meta.get("source_count"),
                "fecha_ingesta": meta.get("ingested_at"),
            }
    return out


def _resumen_delito(df: pd.DataFrame) -> pd.DataFrame:
    """Resumen NACIONAL por título del Código Penal: total, judicializados y tasa por título.

    Usa la taxonomía PROPIA de la Fiscalía (títulos del Código Penal) — no se fuerza un cruce
    con las categorías de la Policía, que no es 1:1 (advertencia declarada en el reporte).
    """
    base = df.groupby(["titulo_delito", "clase_etapa"], as_index=False)["n_procesos"].sum()
    tot = base.groupby("titulo_delito")["n_procesos"].sum()
    jud = base[base["clase_etapa"] == "judicializado"].set_index("titulo_delito")["n_procesos"]
    conoc = base[base["clase_etapa"] != "desconocido"].groupby("titulo_delito")["n_procesos"].sum()
    out = pd.DataFrame({"titulo_delito": tot.index, "total_procesos": tot.values})
    out["n_judicializados"] = out["titulo_delito"].map(jud).fillna(0).astype("int64")
    out["procesos_etapa_conocida"] = out["titulo_delito"].map(conoc).fillna(0).astype("int64")
    out["tasa_judicializacion_pct"] = (
        100 * out["n_judicializados"] / out["procesos_etapa_conocida"].clip(lower=1)
    ).round(2)
    return out.sort_values("total_procesos", ascending=False).reset_index(drop=True)


def _write_report(
    anual: pd.DataFrame,
    resumen: pd.DataFrame,
    delito: pd.DataFrame | None = None,
    procedencia: dict | None = None,
) -> None:
    """Reporte reproducible: embudo nacional (por clase y por etapa cruda) + tasa de
    judicialización (país, por título del Código Penal si el bronze trae la dimensión penal,
    y por año del hecho) + cobertura + conciliación bronze → gold."""
    funnel = anual.groupby("clase_etapa")["n_procesos"].sum().sort_values(ascending=False).to_dict()
    total = int(anual["n_procesos"].sum())
    conocidos = int(sum(v for k, v in funnel.items() if k != "desconocido"))
    judic = int(funnel.get("judicializado", 0))
    # Embudo por etapa CRUDA de la cadena penal (no solo la clase binaria indagación/
    # judicializado): publica cuántos procesos llegan a investigación, a juicio y a ejecución.
    por_etapa = anual.groupby(["etapa", "clase_etapa"], as_index=False)["n_procesos"].sum()
    por_etapa["_orden"] = por_etapa["etapa"].map(_orden_etapa)
    por_etapa = por_etapa.sort_values(["_orden", "n_procesos"], ascending=[True, False])
    # Tasa nacional por AÑO DEL HECHO: muestra el rezago judicial con el dato (la tasa de los
    # años recientes cae porque esos procesos aún no maduran) y hace explícito que las tasas
    # agregadas mezclan cohortes.
    conocidos_anio = (
        anual[anual["clase_etapa"] != "desconocido"].groupby("anio")["n_procesos"].sum()
    )
    judic_anio = anual[anual["clase_etapa"] == "judicializado"].groupby("anio")["n_procesos"].sum()
    report = {
        "fuente": "Fiscalía General de la Nación — Procesos V3 (dbdv-iihs)",
        "grano": "municipio × año × etapa"
        + (" × título del Código Penal" if delito is not None else ""),
        "total_procesos": total,
        "embudo_etapas": {k: int(v) for k, v in funnel.items()},
        "embudo_por_etapa": [
            {"etapa": r.etapa, "clase_etapa": r.clase_etapa, "n_procesos": int(r.n_procesos)}
            for r in por_etapa.itertuples()
        ],
        "tasa_judicializacion_nacional_pct": round(100 * judic / max(conocidos, 1), 2),
        "tasa_por_anio": [
            {
                "anio": int(a),
                "procesos_etapa_conocida": int(conocidos_anio[a]),
                "tasa_judicializacion_pct": round(
                    100 * float(judic_anio.get(a, 0)) / max(int(conocidos_anio[a]), 1), 2
                ),
            }
            for a in sorted(conocidos_anio.index)
        ],
        "cobertura": {
            "municipios": int(anual["cod_municipio"].nunique()),
            "anio_min": int(anual["anio"].min()),
            "anio_max": int(anual["anio"].max()),
        },
        "top_municipios_por_procesos": (
            resumen.nlargest(10, "total_procesos")[
                ["cod_municipio", "municipio", "total_procesos", "tasa_judicializacion_pct"]
            ].to_dict("records")
        ),
    }
    if delito is not None:
        cols = [
            "titulo_delito",
            "total_procesos",
            "n_judicializados",
            "tasa_judicializacion_pct",
        ]
        # El ranking compara solo títulos con volumen suficiente y con título informado: una tasa
        # calculada sobre pocos procesos es ruido, y "Sin información" no es un delito.
        elegibles = delito[
            (delito["procesos_etapa_conocida"] >= _MIN_PROCESOS_TASA)
            & (delito["titulo_delito"] != "Sin información")
        ]
        report["tasa_por_delito"] = {
            "grano": "nacional × título del Código Penal (taxonomía propia de la Fiscalía)",
            "n_titulos": int(len(delito)),
            "umbral_min_procesos_conocidos": _MIN_PROCESOS_TASA,
            "mayor_tasa": elegibles.nlargest(5, "tasa_judicializacion_pct")[cols].to_dict(
                "records"
            ),
            "menor_tasa": elegibles.nsmallest(5, "tasa_judicializacion_pct")[cols].to_dict(
                "records"
            ),
        }
    if procedencia is not None:
        report["procedencia"] = procedencia
    report["advertencias_uso"] = [
        "Rezago judicial: un proceso por un hecho reciente puede seguir en indagación o sin "
        "radicar; los años recientes quedan más subestimados que en la serie de la Policía.",
        "Las tasas agregadas (nacional, municipal y por título) mezclan cohortes de hechos de "
        "2004-2026: un proceso reciente aún puede avanzar de etapa. Sirven para comparar "
        "territorios o delitos entre sí, no años recientes contra antiguos; el bloque "
        "tasa_por_anio muestra ese efecto.",
        "La indagación domina el volumen (la mayoría de noticias no avanza); el valor está en "
        "la TASA de judicialización, no en el conteo bruto.",
        "Noticia criminal/proceso (Fiscalía) ≠ hecho registrado (Policía): capa paralela, no "
        "comparable 1:1; la taxonomía penal (títulos del Código Penal) tampoco es 1:1 con las "
        "categorías de la Policía, por eso el desglose por delito usa la taxonomía propia de "
        "la fuente.",
    ]
    (settings.reports_dir / "justicia.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
