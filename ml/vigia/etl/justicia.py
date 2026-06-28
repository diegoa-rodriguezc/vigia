"""Capa "Justicia" — gold de los procesos de la Fiscalía (independiente de la Policía).

Toma el agregado de bronze (`justicia_procesos.parquet`, ya agrupado por municipio × año ×
etapa: ese parquet lo produce la ingesta por streaming keyset + conteo local, porque la
agregación server-side de la Fiscalía no es viable — ver `soda.fetch_streamed_aggregate`) y produce:

- `gold/justicia_anual.parquet`: serie de procesos por `municipio × año × etapa`.
- `gold/justicia_resumen.parquet`: por municipio, total de procesos y **tasa de judicialización**
  (fracción que supera la indagación → embudo Indagación → Investigación → Juicio → Ejecución).
- `reports/justicia.json`: embudo nacional, tasa de judicialización y cobertura (reproducible).

NO se fusiona con la serie de delitos de la Policía (silver): una *noticia criminal/proceso* no es
un *hecho registrado* por la Policía; mezclarlas sería doble conteo. Es una capa PARALELA cuyo aporte
diferencial es la dimensión de Justicia (`etapa`), ausente en cualquier conteo de delitos.

**Grano municipio × año × etapa (no mensual):** el valor diferencial —el embudo de judicialización—
no necesita el mes. El año va en el grupo (la ingesta agrega localmente, ver `datasets.py`). El
detalle mensual queda como mejora futura: solo añadiría una columna al `group_cols` del streaming.

**Advertencias de uso (documentadas también en docs/):**
- (1) **rezago judicial** — un proceso por un hecho reciente puede seguir en indagación o sin radicar,
  así que los años recientes subcuentan;
- (2) la **indagación domina** (la mayoría de noticias no avanza), por eso el valor está en la *tasa*,
  no en el volumen bruto;
- (3) la taxonomía penal de la Fiscalía no es 1:1 con las categorías de la Policía.
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


def _norm(s: str) -> str:
    """minúsculas + sin tildes, para clasificar la etapa de forma robusta."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn"
    ).lower()


def _clasifica_etapa(etapa: pd.Series) -> pd.Series:
    """Clasifica cada etapa en 'judicializado' | 'indagacion' | 'desconocido'."""
    norm = etapa.map(_norm)
    es_avanzada = norm.apply(lambda n: any(k in n for k in _ADVANCED_KEYS))
    es_indag = norm.str.contains(_INDAGACION_KEY, na=False)
    return pd.Series(
        ["judicializado" if a else "indagacion" if i else "desconocido"
         for a, i in zip(es_avanzada, es_indag, strict=True)],
        index=etapa.index,
    )


def _official_names(df: pd.DataFrame) -> pd.DataFrame:
    """Asigna municipio/departamento oficiales (DIVIPOLA) por código DANE; degrada si falta."""
    from vigia.etl.divipola import load_municipios

    try:
        ref = load_municipios()[
            ["cod_municipio", "municipio", "departamento", "cod_departamento"]
        ]
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
            "No hay bronze de Justicia. Ejecuta `vigia ingest --only justicia_procesos`."
        )
    raw = pd.read_parquet(src)
    log.info("Justicia: %d filas agregadas en bronze", len(raw))

    df = pd.DataFrame(index=raw.index)
    df["cod_municipio"] = _to_dane5(raw["cod_dane_hecho"], "A")
    df["anio"] = pd.to_numeric(raw["a_o_hecho"], errors="coerce")
    df["etapa"] = raw["etapa"].astype("string").str.strip()
    df["n_procesos"] = pd.to_numeric(raw["n_procesos"], errors="coerce").fillna(0).astype("int64")

    # Descarta filas sin municipio/año válidos o fuera de rango (incluye 'Sin Información').
    df = df[
        df["cod_municipio"].notna()
        & df["anio"].between(2003, 2026)
        & (df["n_procesos"] > 0)
    ].copy()
    df["anio"] = df["anio"].astype("int64")
    df["clase_etapa"] = _clasifica_etapa(df["etapa"])

    # Re-agrega por si el DANE de 8→5 colapsó centros poblados al mismo municipio.
    anual = (
        df.groupby(["cod_municipio", "anio", "etapa", "clase_etapa"], as_index=False)[
            "n_procesos"
        ].sum()
    )
    anual = _official_names(anual)

    # Resumen por municipio + tasa de judicialización (sobre etapas CONOCIDAS).
    resumen = anual.groupby("cod_municipio").agg(
        municipio=("municipio", "first"),
        departamento=("departamento", "first"),
        total_procesos=("n_procesos", "sum"),
    ).reset_index()
    judic = (
        anual[anual["clase_etapa"] == "judicializado"]
        .groupby("cod_municipio")["n_procesos"].sum()
    )
    conoc = (
        anual[anual["clase_etapa"] != "desconocido"]
        .groupby("cod_municipio")["n_procesos"].sum()
    )
    resumen["n_judicializados"] = resumen["cod_municipio"].map(judic).fillna(0).astype("int64")
    resumen["procesos_etapa_conocida"] = (
        resumen["cod_municipio"].map(conoc).fillna(0).astype("int64")
    )
    resumen["tasa_judicializacion_pct"] = (
        100 * resumen["n_judicializados"] / resumen["procesos_etapa_conocida"].clip(lower=1)
    ).round(2)

    settings.ensure_dirs()
    anual.to_parquet(settings.gold_dir / "justicia_anual.parquet", index=False)
    resumen.to_parquet(settings.gold_dir / "justicia_resumen.parquet", index=False)
    _write_report(anual, resumen)
    log.info(
        "Justicia gold: %d filas anuales, %d municipios",
        len(anual), resumen["cod_municipio"].nunique(),
    )
    return anual


def _write_report(anual: pd.DataFrame, resumen: pd.DataFrame) -> None:
    """Reporte reproducible: embudo nacional + tasa de judicialización + cobertura."""
    funnel = (
        anual.groupby("clase_etapa")["n_procesos"].sum().sort_values(ascending=False).to_dict()
    )
    total = int(anual["n_procesos"].sum())
    conocidos = int(sum(v for k, v in funnel.items() if k != "desconocido"))
    judic = int(funnel.get("judicializado", 0))
    report = {
        "fuente": "Fiscalía General de la Nación — Procesos V3 (dbdv-iihs)",
        "grano": "municipio × año × etapa",
        "total_procesos": total,
        "embudo_etapas": {k: int(v) for k, v in funnel.items()},
        "tasa_judicializacion_nacional_pct": round(100 * judic / max(conocidos, 1), 2),
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
        "advertencias_uso": [
            "Rezago judicial: un proceso por un hecho reciente puede seguir en indagación o sin "
            "radicar; los años recientes subcuentan más que la serie de la Policía.",
            "La indagación domina el volumen (la mayoría de noticias no avanza); el valor está en "
            "la TASA de judicialización, no en el conteo bruto.",
            "Noticia criminal/proceso (Fiscalía) ≠ hecho registrado (Policía): capa paralela, no "
            "comparable 1:1; la taxonomía penal tampoco es 1:1 con las categorías de la Policía.",
        ],
    }
    (settings.reports_dir / "justicia.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
