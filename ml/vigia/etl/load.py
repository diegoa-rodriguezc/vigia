"""Carga de la capa GOLD a PostgreSQL (las tablas que expone el backend Go).

Crea y rellena las tablas `resumen_municipio`, `serie_mensual` y
`anomalias` usando COPY para eficiencia. El esquema relacional vive aquí para que
el pipeline sea autocontenido.
"""

from __future__ import annotations

import pandas as pd

from vigia.config import settings
from vigia.db import get_conn
from vigia.logging import get_logger

log = get_logger(__name__)

# Cada sentencia se ejecuta por separado (ver _exec_ddl): con conexión en autocommit,
# un lote multi-sentencia se trataría como UNA transacción implícita y, además, las
# migraciones ALTER deben correr ANTES de cualquier índice que dependa de las columnas
# nuevas. Las ALTER ... IF NOT EXISTS hacen segura la re-ejecución de la migración de tablas antiguas.
DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS resumen_municipio (
        cod_municipio TEXT, municipio TEXT, departamento TEXT,
        total_hechos BIGINT, total_delitos BIGINT, total_respuestas BIGINT,
        categorias INT, primer_anio INT, ultimo_anio INT,
        lat DOUBLE PRECISION, lon DOUBLE PRECISION
    )""",
    """CREATE TABLE IF NOT EXISTS serie_mensual (
        cod_municipio TEXT, municipio TEXT, cod_departamento TEXT, departamento TEXT,
        categoria TEXT, naturaleza TEXT, periodo DATE, cantidad BIGINT, anio INT, mes INT
    )""",
    """CREATE TABLE IF NOT EXISTS anomalias (
        cod_municipio TEXT, municipio TEXT, departamento TEXT, categoria TEXT,
        periodo DATE, cantidad BIGINT, score_z DOUBLE PRECISION, severidad TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS justicia_resumen (
        cod_municipio TEXT, municipio TEXT, departamento TEXT,
        total_procesos BIGINT, n_judicializados BIGINT,
        procesos_etapa_conocida BIGINT, tasa_judicializacion_pct DOUBLE PRECISION
    )""",
    """CREATE TABLE IF NOT EXISTS justicia_anual (
        cod_municipio TEXT, anio INT, etapa TEXT, clase_etapa TEXT, n_procesos BIGINT,
        municipio TEXT, departamento TEXT, cod_departamento TEXT
    )""",
    # Migraciones seguras de re-ejecutar (tablas creadas con un esquema anterior), antes de índices.
    "ALTER TABLE resumen_municipio ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION",
    "ALTER TABLE resumen_municipio ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION",
    "ALTER TABLE resumen_municipio ADD COLUMN IF NOT EXISTS total_delitos BIGINT",
    "ALTER TABLE resumen_municipio ADD COLUMN IF NOT EXISTS total_respuestas BIGINT",
    "ALTER TABLE serie_mensual ADD COLUMN IF NOT EXISTS naturaleza TEXT",
    # Índice de serie_mensual
    "CREATE INDEX IF NOT EXISTS idx_serie_mpio_cat ON serie_mensual (cod_municipio, categoria)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_serie_naturaleza_categoria ON serie_mensual (naturaleza, categoria)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_serie_periodo ON serie_mensual (periodo)",
    # Índice de resumen_municipio
    "CREATE INDEX IF NOT EXISTS idx_resumen_delitos ON resumen_municipio (total_delitos DESC)",
    "CREATE INDEX IF NOT EXISTS idx_resumen_departamento ON resumen_municipio ((left(cod_municipio,2)))",
    # Índice de paginación/orden estable de anomalías (coincide con el ORDER BY del backend).
    "CREATE INDEX IF NOT EXISTS idx_anom_periodo ON anomalias (periodo DESC, cod_municipio)",
    "CREATE INDEX IF NOT EXISTS idx_anom_severidad ON anomalias(severidad)",
    # Búsqueda textual sin acentos del backend (`LIKE '%…%'`): un btree no sirve para
    # comodín inicial. pg_trgm + índice GIN sobre la MISMA expresión que usa el backend
    # (`translate(lower(col), 'áéíóúüñ', 'aeiouun')`) la vuelve indexable y evita el seq-scan.
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS idx_anom_muni_trgm ON anomalias "
    "USING gin ((translate(lower(municipio), 'áéíóúüñ', 'aeiouun')) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_anom_depto_trgm ON anomalias "
    "USING gin ((translate(lower(departamento), 'áéíóúüñ', 'aeiouun')) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_anom_cat_trgm ON anomalias "
    "USING gin ((translate(lower(categoria), 'áéíóúüñ', 'aeiouun')) gin_trgm_ops)",
    # Justicia: ranking por volumen, embudo nacional por etapa y drill-down por municipio.
    "CREATE INDEX IF NOT EXISTS idx_justicia_resumen_total ON justicia_resumen (total_procesos DESC)",
    "CREATE INDEX IF NOT EXISTS idx_justicia_anual_muni ON justicia_anual (cod_municipio)",
    "CREATE INDEX IF NOT EXISTS idx_justicia_anual_etapa ON justicia_anual (etapa)",
]


def _exec_ddl(conn) -> None:
    for stmt in DDL_STATEMENTS:
        conn.execute(stmt)


def _to_native(v):
    """Convierte NA/NaN/NaT -> None y escalares numpy/pandas -> tipos Python nativos."""
    if v is None or v is pd.NA:
        return None
    if hasattr(v, "item"):  # numpy.int64 / numpy.float64 / etc.
        v = v.item()
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def _copy_df(conn, table: str, df: pd.DataFrame, columns: list[str]) -> None:
    """Inserta un DataFrame en una tabla con COPY, normalizando NA y tipos numpy."""
    conn.execute(f"TRUNCATE {table}")
    records = df[columns].astype(object).where(pd.notnull(df[columns]), None)
    with conn.cursor().copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in records.itertuples(index=False, name=None):
            copy.write_row(tuple(_to_native(v) for v in row))


def load_gold() -> None:
    """Carga los tres artefactos gold a PostgreSQL."""
    gold = settings.gold_dir
    with get_conn() as conn:
        _exec_ddl(conn)

        resumen = pd.read_parquet(gold / "resumen_municipio.parquet")
        _copy_df(
            conn,
            "resumen_municipio",
            resumen,
            [
                "cod_municipio",
                "municipio",
                "departamento",
                "total_hechos",
                "total_delitos",
                "total_respuestas",
                "categorias",
                "primer_anio",
                "ultimo_anio",
                "lat",
                "lon",
            ],
        )
        log.info("Cargado resumen_municipio: %d filas", len(resumen))

        serie = pd.read_parquet(gold / "serie_mensual.parquet")
        serie = serie.assign(periodo=pd.to_datetime(serie["periodo"]).dt.date)
        _copy_df(
            conn,
            "serie_mensual",
            serie,
            [
                "cod_municipio",
                "municipio",
                "cod_departamento",
                "departamento",
                "categoria",
                "naturaleza",
                "periodo",
                "cantidad",
                "anio",
                "mes",
            ],
        )
        log.info("Cargado serie_mensual: %d filas", len(serie))

        anom_path = gold / "anomalias.parquet"
        if anom_path.exists():
            anom = pd.read_parquet(anom_path)
            if not anom.empty:
                anom = anom.assign(periodo=pd.to_datetime(anom["periodo"]).dt.date)
            _copy_df(
                conn,
                "anomalias",
                anom,
                [
                    "cod_municipio",
                    "municipio",
                    "departamento",
                    "categoria",
                    "periodo",
                    "cantidad",
                    "score_z",
                    "severidad",
                ],
            )
            log.info("Cargado anomalias: %d filas", len(anom))

        # Capa "Justicia" (Fiscalía): se carga si su gold existe (degrada con elegancia si no).
        jr_path = gold / "justicia_resumen.parquet"
        ja_path = gold / "justicia_anual.parquet"
        if jr_path.exists() and ja_path.exists():
            jr = pd.read_parquet(jr_path)
            _copy_df(
                conn,
                "justicia_resumen",
                jr,
                [
                    "cod_municipio",
                    "municipio",
                    "departamento",
                    "total_procesos",
                    "n_judicializados",
                    "procesos_etapa_conocida",
                    "tasa_judicializacion_pct",
                ],
            )
            log.info("Cargado justicia_resumen: %d filas", len(jr))

            ja = pd.read_parquet(ja_path)
            _copy_df(
                conn,
                "justicia_anual",
                ja,
                [
                    "cod_municipio",
                    "anio",
                    "etapa",
                    "clase_etapa",
                    "n_procesos",
                    "municipio",
                    "departamento",
                    "cod_departamento",
                ],
            )
            log.info("Cargado justicia_anual: %d filas", len(ja))
        else:
            log.info("Capa Justicia no encontrada en gold; se omite su carga.")
    log.info("Carga a PostgreSQL completada.")
