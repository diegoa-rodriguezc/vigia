"""Cliente para la API SODA2 (Socrata) de datos.gov.co.

Abstracción del cliente exploratorio del notebook `001_Dataset.ipynb`:
sesión con reintentos automáticos (429/5xx) y paginación por `$limit`/`$offset`.
"""

from __future__ import annotations

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from vigia.logging import get_logger

log = get_logger(__name__)

SODA_MAX_PAGE = 50_000  # tope de filas por petición en SODA2


def _build_session(app_token: str | None = None) -> requests.Session:
    """Crea una sesión HTTP con keep-alive y reintentos exponenciales."""
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if app_token:
        session.headers.update({"X-App-Token": app_token})
    return session


def fetch_dataset(
    soda_id: str,
    *,
    page_size: int = SODA_MAX_PAGE,
    max_rows: int | None = None,
    app_token: str | None = None,
    order: str = ":id",
    timeout: int = 60,
) -> pd.DataFrame:
    """Descarga un dataset SODA2 completo paginando de forma estable.

    Args:
        soda_id: identificador del recurso (`.../resource/<soda_id>.json`).
        page_size: filas por petición (máx. 50.000).
        max_rows: tope total de filas (None = todas).
        app_token: X-App-Token de Socrata para mayor cuota (opcional).
        order: columna de orden estable para paginar (`:id` por defecto).

    Returns:
        DataFrame con todas las filas (todo como texto, tal cual SODA2).
    """
    url = f"https://www.datos.gov.co/resource/{soda_id}.json"
    session = _build_session(app_token)
    page_size = min(page_size, SODA_MAX_PAGE)

    chunks: list[pd.DataFrame] = []
    offset = 0
    while True:
        params = {"$limit": page_size, "$offset": offset, "$order": order}
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        chunks.append(pd.DataFrame(rows))
        got = len(rows)
        offset += got
        log.info("  %s: %d filas acumuladas", soda_id, offset)
        if got < page_size:
            break
        if max_rows is not None and offset >= max_rows:
            break

    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    if max_rows is not None:
        df = df.head(max_rows)
    return df


def fetch_streamed_aggregate(
    soda_id: str,
    group_cols: list[str],
    *,
    count_as: str = "n",
    where: str | None = None,
    app_token: str | None = None,
    page_size: int = SODA_MAX_PAGE,
    timeout: int = 90,
) -> pd.DataFrame:
    """Agrega un dataset SODA2 ENORME trayendo solo las columnas de grupo y contando LOCALMENTE.

    Para micro-dato gigante (p. ej. ~23 M de procesos de la Fiscalía) la agregación server-side
    (`count(1)`+`$group`) **no es viable**: el backend de esos datasets es tan lento que hasta un
    `count(*)` tarda ~80 s y cualquier `$group` revienta el timeout (500 / >120 s). Un app token
    NO lo arregla (sube la cuota de FRECUENCIA, no el límite de CÓMPUTO por consulta).

    La alternativa que SÍ escala: paginar por **keyset** (`:id > último`, no `$offset`, que se
    degrada en profundidad) trayendo **solo `group_cols`** (columnas estrechas → páginas de 50.000
    filas en ~2-3 s) y agregar con un acumulador en memoria. Las claves únicas son pocas (p. ej.
    municipio×año×etapa ≈ 1e5), así que el acumulado es minúsculo aunque la fuente tenga decenas
    de millones de filas. Resultado idéntico al `$group`, pero reproducible y robusto sin token.

    Returns:
        DataFrame con `group_cols` + la columna de conteo `count_as` (entera).
    """
    url = f"https://www.datos.gov.co/resource/{soda_id}.json"
    session = _build_session(app_token)
    page_size = min(page_size, SODA_MAX_PAGE)
    select = ",".join([*group_cols, ":id"])

    acc: list[pd.DataFrame] = []  # agregados parciales por página (se colapsan al final)
    last_id: str | None = None
    total = 0
    while True:
        # Keyset: orden estable por :id y avance con :id > último (evita el coste del $offset hondo).
        clause = f':id > "{last_id}"' if last_id else None
        full_where = " AND ".join(c for c in (where and f"({where})", clause) if c) or None
        params = {"$select": select, "$order": ":id", "$limit": page_size}
        if full_where:
            params["$where"] = full_where
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        page = pd.DataFrame(rows)
        last_id = page[":id"].iloc[-1]
        # Agrega ya la página (vectorizado) para no acumular millones de filas crudas en RAM.
        part = page.groupby(group_cols, dropna=False).size().reset_index(name=count_as)
        acc.append(part)
        total += len(rows)
        if total % (page_size * 10) == 0:
            log.info("  %s (stream): %d filas leídas", soda_id, total)
        if len(rows) < page_size:
            break

    if not acc:
        return pd.DataFrame()
    # Colapsa los parciales: re-agrupa y suma los conteos por clave.
    out = pd.concat(acc, ignore_index=True).groupby(group_cols, dropna=False, as_index=False)[
        count_as
    ].sum()
    log.info("  %s (stream): %d filas leídas -> %d grupos", soda_id, total, len(out))
    return out
