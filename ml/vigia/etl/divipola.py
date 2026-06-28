"""Tabla maestra DIVIPOLA (DANE) — nombres oficiales y coordenadas por municipio.

Fuente oficial para asignar el nombre canónico de departamentos y municipios a partir
del código DANE, evitando las inconsistencias de escritura de las fuentes delictivas.
Provee además la coordenada de la cabecera municipal para el mapa.
"""

from __future__ import annotations

import pandas as pd

from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)


def _parse_coord(value: object) -> float | None:
    """Convierte coordenadas de DIVIPOLA ('4,649251', '-75,581,775') a float.

    El separador decimal es la coma; pueden venir comas adicionales de agrupación,
    por lo que se toma la primera como decimal y se descartan las demás.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    neg = s.startswith("-")
    digits = s.lstrip("-")
    parts = digits.split(",")
    norm = parts[0] if len(parts) == 1 else parts[0] + "." + "".join(parts[1:])
    try:
        v = float(norm)
    except ValueError:
        return None
    if not (-90 <= v <= 90) and abs(v) > 180:
        return None
    return -v if neg else v


def load_municipios() -> pd.DataFrame:
    """Devuelve una fila por municipio con nombre oficial, departamento y coordenadas.

    Prefiere la cabecera municipal (tipo 'CM') para el nombre y la coordenada; si un
    municipio solo tiene centros poblados, usa el primero disponible.
    """
    src = settings.bronze_dir / "divipola.parquet"
    if not src.exists():
        raise RuntimeError("DIVIPOLA ausente en bronze. Ejecuta `vigia ingest --only divipola`.")
    df = pd.read_parquet(src)

    out = pd.DataFrame()
    out["cod_municipio"] = (
        df["codigo_municipio"].astype("string").str.replace(r"\D", "", regex=True).str.zfill(5)
    )
    out["cod_departamento"] = (
        df["codigo_departamento"].astype("string").str.replace(r"\D", "", regex=True).str.zfill(2)
    )
    out["municipio"] = df["nombre_municipio"].astype("string").str.strip()
    out["departamento"] = df["nombre_departamento"].astype("string").str.strip()
    out["lat"] = df["latitud"].map(_parse_coord)
    out["lon"] = df["longitud"].map(_parse_coord)
    # Prioriza la cabecera municipal (CM) como fila canónica del municipio.
    out["_es_cabecera"] = (df["tipo_centro_poblado"].astype("string") == "CM").astype(int)

    muni = (
        out.sort_values(["cod_municipio", "_es_cabecera"], ascending=[True, False])
        .drop_duplicates("cod_municipio")
        .drop(columns="_es_cabecera")
        .reset_index(drop=True)
    )
    log.info("DIVIPOLA: %d municipios oficiales cargados", len(muni))
    return muni
