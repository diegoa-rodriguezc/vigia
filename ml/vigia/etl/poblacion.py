"""Población municipal (DANE) — denominador para tasas por 100.000 habitantes.

Fuente oficial: *proyecciones y retroproyecciones de población municipal por área*
del DANE (CNPV 2018, actualización post-COVID). datos.gov.co NO publica una versión
nacional municipal por año —solo cargas municipales/departamentales sueltas, inservibles
para cubrir los ~1.100 municipios—, por lo que se usa el archivo oficial del DANE, que es
dato abierto de una entidad pública.
Cubre 2005-2035; los años previos de la serie delictiva (2003-2004)
se respaldan con el primer año disponible al cruzar en `gold` (clip de año).

La población habilita el modelado en TASAS por 100.000 habitantes (comparables entre Bogotá
y un municipio pequeño) y entra como feature exógena al pronóstico —la primera señal del
modelo que no es autorregresiva—.
"""

from __future__ import annotations

import hashlib
import io
import json
import unicodedata
from datetime import UTC, datetime

import pandas as pd
import requests

from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)

# Archivos oficiales del DANE (proyección municipal por área). Comparten los MISMOS
# nombres de columna (DP, DPNOM, MPIO, DPMP, AÑO, ÁREA GEOGRÁFICA, Población) aunque
# difieren en hoja, fila de encabezado y orden de columnas → se localiza el encabezado
# y se selecciona por nombre normalizado (no por posición).
POBLACION_SOURCES: list[str] = [
    "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/"
    "DCD-area-proypoblacion-Mun-2005-2019.xlsx",
    "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/"
    "DCD-area-proypoblacion-Mun-2020-2035-ActPostCOVID-19.xlsx",
]

_AREA_TOTAL = "TOTAL"  # solo el total municipal (cabecera + resto), no el desglose por área


def _norm(s: object) -> str:
    """Normaliza un encabezado: sin acentos, mayúsculas, sin espacios extremos."""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().upper()


def _pick(cols: list[str], *, equals: str | None = None, contains: str | None = None) -> str:
    """Devuelve el nombre de columna real cuyo encabezado normalizado coincide."""
    for c in cols:
        n = _norm(c)
        if (equals is not None and n == equals) or (contains is not None and contains in n):
            return c
    raise RuntimeError(f"Columna no encontrada (equals={equals}, contains={contains}) en {cols}")


def _read_one(content: bytes) -> pd.DataFrame:
    """Procesa un Excel de proyección DANE a `[cod_municipio, anio, poblacion]` (solo Total)."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None, dtype=object)
    hdr = None
    for i in range(min(30, len(raw))):
        norm_row = {_norm(v) for v in raw.iloc[i].tolist()}
        if "MPIO" in norm_row and any(n.startswith("POBLACI") for n in norm_row):
            hdr = i
            break
    if hdr is None:
        raise RuntimeError("No se encontró el encabezado (MPIO/Población) en el Excel del DANE")

    cols = [str(v).strip() for v in raw.iloc[hdr].tolist()]
    df = raw.iloc[hdr + 1 :].copy()
    df.columns = cols

    cod_c = _pick(cols, equals="MPIO")
    anio_c = _pick(cols, equals="ANO")  # 'AÑO' -> 'ANO' al quitar acentos
    area_c = _pick(cols, contains="AREA")
    pob_c = _pick(cols, contains="POBLACI")

    area_norm = df[area_c].map(_norm)
    df = df[area_norm == _AREA_TOTAL]

    cod = df[cod_c].astype("string").str.replace(r"\D", "", regex=True).str.zfill(5)
    out = pd.DataFrame(
        {
            "cod_municipio": cod,
            "anio": pd.to_numeric(df[anio_c], errors="coerce").astype("Int64"),
            "poblacion": pd.to_numeric(df[pob_c], errors="coerce").astype("Int64"),
        }
    )
    out = out.dropna(subset=["cod_municipio", "anio", "poblacion"])
    # Descarta marcadores de código en blanco (mismo criterio que silver._to_dane5).
    out = out[out["cod_municipio"].str.slice(0, 2) != "00"]
    return out[out["poblacion"] > 0]


def ingest_poblacion() -> pd.DataFrame:
    """Descarga y consolida la población municipal del DANE en `bronze/poblacion.parquet`.

    Concatena los archivos histórico (2005-2019) y proyectado (2020-2035), conservando una sola
    fila por `(cod_municipio, anio)`. Persiste el linaje en `poblacion.meta.json`.
    """
    settings.ensure_dirs()
    frames: list[pd.DataFrame] = []
    sources_meta: list[dict] = []
    headers = {"User-Agent": "VigIA/0.1 (+https://datos.gov.co) data-pipeline"}
    for url in POBLACION_SOURCES:
        log.info("Descargando población DANE: %s", url)
        resp = requests.get(url, timeout=120, headers=headers)
        resp.raise_for_status()
        df = _read_one(resp.content)
        frames.append(df)
        # Checksum del archivo descargado (linaje verificable: los hashes de referencia están
        # publicados en docs/DATASETS.md — si el DANE reemplaza el archivo, el meta lo delata).
        sources_meta.append(
            {
                "url": url,
                "filas": int(len(df)),
                "bytes": len(resp.content),
                "sha256": hashlib.sha256(resp.content).hexdigest(),
            }
        )

    pob = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["cod_municipio", "anio"])
        .drop_duplicates(["cod_municipio", "anio"], keep="last")
        .reset_index(drop=True)
    )

    out = settings.bronze_dir / "poblacion.parquet"
    pob.to_parquet(out, index=False)
    meta = {
        "dataset_id": "poblacion",
        "name": "Proyecciones de población municipal por área (DANE, CNPV 2018)",
        "filas": int(len(pob)),
        "municipios": int(pob["cod_municipio"].nunique()),
        "anio_min": int(pob["anio"].min()),
        "anio_max": int(pob["anio"].max()),
        "fuentes": sources_meta,
        "nota": "datos.gov.co no publica esta serie nacional municipal; fuente oficial dane.gov.co",
        "ingested_at": datetime.now(UTC).isoformat(),
    }
    (settings.bronze_dir / "poblacion.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(
        "Población DANE: %d filas (%d municipios, %d-%d)",
        len(pob),
        meta["municipios"],
        meta["anio_min"],
        meta["anio_max"],
    )
    return pob


def load_poblacion() -> pd.DataFrame:
    """Devuelve `[cod_municipio, anio, poblacion]`; lanza si aún no se ha descargado."""
    src = settings.bronze_dir / "poblacion.parquet"
    if not src.exists():
        raise RuntimeError(
            "Población ausente en bronze. Ejecute `vigia ingest` (o `ingest_poblacion`)."
        )
    return pd.read_parquet(src)
