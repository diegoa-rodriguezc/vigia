"""Capa GOLD — agregados listos para servir y para modelar.

Produce:
- `serie_mensual.parquet`: serie temporal `municipio × categoria × (anio, mes)`.
- `resumen_municipio.parquet`: KPIs por municipio (para tablero y data cards del RAG).
- `resumen_categoria.parquet`: KPIs por categoría/año (para tablero).
"""

from __future__ import annotations

import pandas as pd

from vigia.config import settings
from vigia.datasets import RESPONSE_CATEGORIES
from vigia.logging import get_logger

log = get_logger(__name__)


def _load_silver() -> pd.DataFrame:
    src = settings.silver_dir / "eventos.parquet"
    if not src.exists():
        raise RuntimeError("Silver ausente. Ejecute primero `vigia clean`.")
    return pd.read_parquet(src)


def _attach_poblacion(series: pd.DataFrame) -> pd.DataFrame:
    """Añade `poblacion` (DANE) por `(cod_municipio, anio)`; habilita tasas por 100.000 hab.

    La proyección DANE cubre 2005-2035; los años fuera de rango (2003-2004, o futuros) se
    respaldan con el año disponible más cercano (clip), evitando nulos en los extremos de la
    serie. Si la población no se ha ingerido, la columna queda nula y el modelo opera sin
    tasas (degradación elegante, como con DIVIPOLA).
    """
    try:
        from vigia.etl.poblacion import load_poblacion

        pob = load_poblacion()
    except RuntimeError as exc:
        log.warning("Población no añadida (%s); se modela sin tasas por 100.000 hab.", exc)
        series["poblacion"] = pd.NA
        return series

    amin, amax = int(pob["anio"].min()), int(pob["anio"].max())
    lookup = series["anio"].clip(amin, amax).astype("int64")
    merged = (
        series.assign(_anio_lk=lookup)
        .merge(
            pob.rename(columns={"anio": "_anio_lk"}),
            on=["cod_municipio", "_anio_lk"],
            how="left",
        )
        .drop(columns="_anio_lk")
    )
    cobertura = merged["poblacion"].notna().mean()
    log.info("Población DANE cruzada con %.1f%% de las filas de la serie mensual", 100 * cobertura)
    return merged


def build_monthly_series(eventos: pd.DataFrame) -> pd.DataFrame:
    """Serie mensual de hechos por municipio y categoría, con calendario continuo.

    Rellena los meses sin eventos con 0 para no romper los modelos de series.
    """
    eventos = eventos.copy()
    eventos["periodo"] = pd.to_datetime(dict(year=eventos["anio"], month=eventos["mes"], day=1))
    grp = (
        eventos.groupby(
            [
                "cod_departamento",
                "departamento",
                "cod_municipio",
                "municipio",
                "categoria",
                "periodo",
            ],
            dropna=False,
        )["cantidad"]
        .sum()
        .reset_index()
    )

    # Reindexa cada (municipio, categoria) sobre SU PROPIO rango activo (no un
    # calendario global): así no se inventan años de ceros para municipios que solo
    # aparecen tarde, lo que corrompería el modelo e inflaría el error. Los huecos
    # internos sí se rellenan con 0 (mes sin hechos = 0 legítimo).
    keys = ["cod_municipio", "municipio", "cod_departamento", "departamento", "categoria"]

    filled: list[pd.DataFrame] = []
    for key_vals, sub in grp.groupby(keys, dropna=False):
        cal = pd.period_range(sub["periodo"].min(), sub["periodo"].max(), freq="M").to_timestamp()
        s = sub.set_index("periodo")["cantidad"].reindex(cal, fill_value=0)
        block = pd.DataFrame({"periodo": cal, "cantidad": s.values})
        for col, val in zip(keys, key_vals, strict=False):
            block[col] = val
        filled.append(block)

    series = pd.concat(filled, ignore_index=True)
    series["anio"] = series["periodo"].dt.year
    series["mes"] = series["periodo"].dt.month
    series = _attach_poblacion(series)
    # Naturaleza de la serie: distingue incidencia delictiva de actividad institucional
    # (capturas/incautaciones/recuperaciones), para poder filtrarlas más abajo.
    es_respuesta = series["categoria"].isin(RESPONSE_CATEGORIES)
    series["naturaleza"] = pd.Series("delito", index=series.index).mask(es_respuesta, "respuesta")
    return series


def build_gold() -> dict[str, pd.DataFrame]:
    """Construye y persiste todos los artefactos de la capa gold."""
    settings.ensure_dirs()
    eventos = _load_silver()

    series = build_monthly_series(eventos)
    series.to_parquet(settings.gold_dir / "serie_mensual.parquet", index=False)
    log.info("Serie mensual de la capa gold escrita: %d filas", len(series))

    # KPIs por municipio. Se agrupa por el código DANE (clave estable) y se elige el
    # nombre canónico (el más frecuente), evitando duplicar municipios por variaciones
    # de escritura entre fuentes.
    #
    # `total_hechos` es el gran total (todas las categorías), pero se DESGLOSA en
    # `total_delitos` (incidencia delictiva, lo que se quiere prevenir) y
    # `total_respuestas` (capturas/incautaciones/recuperaciones, resultado operativo),
    # para que el tablero no presente como "incidencia" lo que en realidad es respuesta.
    es_respuesta = eventos["categoria"].isin(RESPONSE_CATEGORIES)
    eventos = eventos.assign(
        _cant_delito=eventos["cantidad"].where(~es_respuesta, 0),
        _cant_respuesta=eventos["cantidad"].where(es_respuesta, 0),
    )
    resumen_mpio = (
        eventos.groupby("cod_municipio", dropna=False)
        .agg(
            total_hechos=("cantidad", "sum"),
            total_delitos=("_cant_delito", "sum"),
            total_respuestas=("_cant_respuesta", "sum"),
            categorias=("categoria", "nunique"),
            primer_anio=("anio", "min"),
            ultimo_anio=("anio", "max"),
        )
        .reset_index()
    )
    nombres = (
        eventos.groupby(["cod_municipio", "municipio", "departamento"], dropna=False)
        .size()
        .reset_index(name="_n")
        .sort_values("_n", ascending=False)
        .drop_duplicates("cod_municipio")[["cod_municipio", "municipio", "departamento"]]
    )
    resumen_mpio = (
        resumen_mpio.merge(nombres, on="cod_municipio", how="left").sort_values(
            "total_delitos", ascending=False
        )  # ranking por incidencia delictiva
    )
    # Coordenadas oficiales (cabecera municipal DANE) para el mapa del tablero.
    try:
        from vigia.etl.divipola import load_municipios

        coords = load_municipios()[["cod_municipio", "lat", "lon"]]
        resumen_mpio = resumen_mpio.merge(coords, on="cod_municipio", how="left")
    except RuntimeError as exc:
        log.warning("Coordenadas DIVIPOLA no añadidas (%s)", exc)
        resumen_mpio["lat"] = None
        resumen_mpio["lon"] = None
    resumen_mpio.to_parquet(settings.gold_dir / "resumen_municipio.parquet", index=False)

    # KPIs por categoría y año (para tablero), con su naturaleza (delito/respuesta).
    resumen_cat = (
        eventos.groupby(["categoria", "anio"], dropna=False)["cantidad"].sum().reset_index()
    )
    resumen_cat["naturaleza"] = "delito"
    resumen_cat.loc[resumen_cat["categoria"].isin(RESPONSE_CATEGORIES), "naturaleza"] = "respuesta"
    resumen_cat.to_parquet(settings.gold_dir / "resumen_categoria.parquet", index=False)

    log.info(
        "Capa gold lista: %d municipios, %d categorías",
        len(resumen_mpio),
        eventos["categoria"].nunique(),
    )
    return {"serie": series, "municipio": resumen_mpio, "categoria": resumen_cat}
