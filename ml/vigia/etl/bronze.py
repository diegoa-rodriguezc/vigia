"""Capa BRONZE — copia fiel del crudo descargado de SODA2 con linaje.

Cada dataset se guarda como Parquet en `data/bronze/<id>.parquet` junto con un
archivo de metadatos `<id>.meta.json` (fuente, fecha de ingesta, nº de filas, hash).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from vigia.config import settings
from vigia.datasets import ALL_DATASETS, AggregatedSpec, DatasetSpec
from vigia.ingest.soda import fetch_dataset, fetch_streamed_aggregate
from vigia.logging import get_logger

log = get_logger(__name__)


def _dataframe_hash(df: pd.DataFrame) -> str:
    """Hash estable del contenido para versionado/auditoría."""
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()


def ingest_one(spec: DatasetSpec) -> pd.DataFrame:
    """Descarga un dataset y lo persiste en la capa bronze con su linaje."""
    settings.ensure_dirs()
    log.info("Ingestando %s (%s)…", spec.id, spec.soda_id)
    df = fetch_dataset(
        spec.soda_id,
        max_rows=settings.soda_max_rows,
        app_token=settings.soda_app_token,
    )
    out = settings.bronze_dir / f"{spec.id}.parquet"
    df.to_parquet(out, index=False)

    meta = {
        "dataset_id": spec.id,
        "soda_id": spec.soda_id,
        "name": spec.name,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "content_hash": _dataframe_hash(df) if not df.empty else None,
        "ingested_at": datetime.now(UTC).isoformat(),
        "source_url": f"https://www.datos.gov.co/resource/{spec.soda_id}.json",
    }
    (settings.bronze_dir / f"{spec.id}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("  -> %s (%d filas)", out.name, len(df))
    return df


def ingest_aggregated(spec: AggregatedSpec) -> pd.DataFrame:
    """Ingiere una fuente ENORME por streaming de columnas + agregación LOCAL, con linaje.

    Para micro-dato inviable de agregar server-side (p. ej. ~23 M de procesos de la Fiscalía,
    cuyo backend revienta el timeout en cualquier `$group`): se traen solo `group_cols` por
    keyset y se cuentan en memoria (ver `soda.fetch_streamed_aggregate`).
    """
    settings.ensure_dirs()
    log.info("Ingestando (stream+agregación local) %s (%s)…", spec.id, spec.soda_id)
    df = fetch_streamed_aggregate(
        spec.soda_id,
        list(spec.group_cols),
        count_as=spec.count_as,
        where=spec.where,
        app_token=settings.soda_app_token,
    )
    out = settings.bronze_dir / f"{spec.id}.parquet"
    df.to_parquet(out, index=False)
    meta = {
        "dataset_id": spec.id,
        "soda_id": spec.soda_id,
        "name": spec.name,
        "aggregated": True,
        "mode": "stream+local",
        "group_cols": list(spec.group_cols),
        "count_as": spec.count_as,
        "where": spec.where,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "content_hash": _dataframe_hash(df) if not df.empty else None,
        "ingested_at": datetime.now(UTC).isoformat(),
        "source_url": f"https://www.datos.gov.co/resource/{spec.soda_id}.json",
    }
    (settings.bronze_dir / f"{spec.id}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("  -> %s (%d filas agregadas)", out.name, len(df))
    return df


def ingest_all(only: list[str] | None = None) -> None:
    """Ingesta todo el catálogo (o un subconjunto por `only`)."""
    specs = [s for s in ALL_DATASETS.values() if only is None or s.id in only]
    for spec in specs:
        try:
            ingest_one(spec)
        except Exception as exc:  # noqa: BLE001 — robustez: un fallo no detiene el lote
            log.error("Fallo ingestando %s: %s", spec.id, exc)

    # Población municipal DANE (no SODA: archivo oficial dane.gov.co). Habilita las tasas
    # por 100k y la feature exógena del pronóstico. Se trata aparte del catálogo SODA.
    if only is None or "poblacion" in only:
        try:
            from vigia.etl.poblacion import ingest_poblacion

            ingest_poblacion()
        except Exception as exc:  # noqa: BLE001 — un fallo de red no detiene el pipeline
            log.error("Fallo ingestando población DANE: %s", exc)

    # Capa "Justicia": procesos de la Fiscalía, AGREGADOS en la API.
    if only is None or "justicia_procesos" in only:
        try:
            from vigia.datasets import JUSTICIA_PROCESOS

            ingest_aggregated(JUSTICIA_PROCESOS)
        except Exception as exc:  # noqa: BLE001 — un fallo de red no detiene el pipeline
            log.error("Fallo ingestando Justicia (Fiscalía): %s", exc)
