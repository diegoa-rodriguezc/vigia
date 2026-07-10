"""Cliente para la API SODA2 (Socrata) de datos.gov.co.

Abstracción del cliente exploratorio del notebook `001_Dataset.ipynb`:
sesión con reintentos automáticos (429/5xx) y paginación por `$limit`/`$offset`.
"""

from __future__ import annotations

import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from vigia.logging import get_logger

log = get_logger(__name__)

SODA_MAX_PAGE = 50_000  # tope de filas por petición en SODA2
# Tope de filas de los agregados parciales del streaming antes de re-agruparlos (acota la RAM
# de `fetch_streamed_aggregate` con grupos anchos; ver el colapso intermedio en esa función).
_ACC_COLLAPSE_ROWS = 2_000_000
# Reintentos POR PÁGINA del streaming (además de los reintentos 429/5xx de la sesión): un corte
# a mitad del cuerpo de la respuesta (IncompleteRead) escapa al Retry de urllib3 y, sin esto,
# una sola falla transitoria pierde ~media hora de avance. El keyset hace el reintento seguro:
# re-pedir la misma página (:id > último) produce el mismo resultado.
_PAGE_RETRIES = 4


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

    Para micro-dato gigante (p. ej. ~23 millones de procesos de la Fiscalía) la agregación
    server-side (`count(1)`+`$group`) **no es viable**: el backend de esos datasets es tan
    lento que hasta un `count(*)` tarda ~80 s y cualquier `$group` revienta el timeout
    (500 / >120 s). Un app token NO lo arregla (sube la cuota de FRECUENCIA, no el límite
    de CÓMPUTO por consulta).

    La alternativa que SÍ escala: paginar por **keyset** (`:id > último`, no `$offset`, que se
    degrada en profundidad) trayendo **solo `group_cols`** (columnas estrechas → páginas de 50.000
    filas en ~2-3 s) y agregar con un acumulador en memoria. Las claves únicas son pocas (p. ej.
    municipio×año×etapa ≈ 1e5), así que el acumulado es minúsculo aunque la fuente tenga decenas
    de millones de filas. Resultado idéntico al `$group`, pero reproducible y robusto sin token.

    Returns:
        DataFrame con `group_cols` + la columna de conteo `count_as` (entera). El total de
        filas de ORIGEN leídas queda en `df.attrs["source_rows"]` (linaje: la suma de los
        conteos debe calzar con ese total, cada fila de origen cuenta exactamente 1).
    """
    url = f"https://www.datos.gov.co/resource/{soda_id}.json"
    session = _build_session(app_token)
    page_size = min(page_size, SODA_MAX_PAGE)
    select = ",".join([*group_cols, ":id"])

    def _collapse(parts: list[pd.DataFrame]) -> pd.DataFrame:
        """Re-agrupa los parciales y suma los conteos por clave."""
        return (
            pd.concat(parts, ignore_index=True)
            .groupby(group_cols, dropna=False, as_index=False)[count_as]
            .sum()
        )

    acc: list[pd.DataFrame] = []  # agregados parciales por página (se colapsan por tramos)
    acc_rows = 0  # filas acumuladas en los parciales (dispara el colapso intermedio)
    last_id: str | None = None
    total = 0
    while True:
        # Keyset: orden estable por :id y avance con :id > último (evita el $offset hondo).
        clause = f':id > "{last_id}"' if last_id else None
        full_where = " AND ".join(c for c in (where and f"({where})", clause) if c) or None
        params = {"$select": select, "$order": ":id", "$limit": page_size}
        if full_where:
            params["$where"] = full_where
        for intento in range(_PAGE_RETRIES):
            try:
                resp = session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                rows = resp.json()
                break
            except (requests.RequestException, ValueError) as exc:
                # ValueError: cuerpo no-JSON (respuesta truncada/errónea del backend). Re-pedir
                # la misma página es seguro: el $where por :id no avanza hasta que la página llega.
                if intento == _PAGE_RETRIES - 1:
                    raise
                espera = 5 * 2**intento
                log.warning(
                    "  %s (stream): error transitorio en la página (%s); reintento %d/%d en %d s",
                    soda_id,
                    exc,
                    intento + 1,
                    _PAGE_RETRIES - 1,
                    espera,
                )
                time.sleep(espera)
        if not rows:
            break
        page = pd.DataFrame(rows)
        last_id = page[":id"].iloc[-1]
        # Agrega ya la página (vectorizado) para no acumular millones de filas crudas en RAM.
        part = page.groupby(group_cols, dropna=False).size().reset_index(name=count_as)
        acc.append(part)
        acc_rows += len(part)
        # Colapso intermedio: con un grupo ancho (p. ej. municipio×año×etapa×título) los parciales
        # de cientos de páginas suman millones de filas; re-agruparlos por tramos acota la RAM a un
        # tamaño fijo sin cambiar el resultado (la suma de conteos es asociativa).
        if acc_rows > _ACC_COLLAPSE_ROWS:
            acc = [_collapse(acc)]
            acc_rows = len(acc[0])
        total += len(rows)
        if total % (page_size * 10) == 0:
            log.info("  %s (stream): %d filas leídas", soda_id, total)
        if len(rows) < page_size:
            break

    if not acc:
        out = pd.DataFrame()
    else:
        out = _collapse(acc)
        log.info("  %s (stream): %d filas leídas -> %d grupos", soda_id, total, len(out))
    out.attrs["source_rows"] = total  # linaje: filas de origen leídas (≡ suma de los conteos)
    return out


def fetch_count(
    soda_id: str,
    *,
    where: str | None = None,
    app_token: str | None = None,
    timeout: int = 180,
) -> int | None:
    """`count(1)` server-side en UNA petición, para CONCILIAR la ingesta por streaming.

    En los datasets enormes es lento (~80 s en la fuente de la Fiscalía) pero, a diferencia
    del `$group`, sí responde. Devuelve None si el servidor no contesta a tiempo (la
    conciliación es linaje deseable, no requisito: su ausencia no debe tumbar la ingesta).
    """
    url = f"https://www.datos.gov.co/resource/{soda_id}.json"
    session = _build_session(app_token)
    params: dict[str, str] = {"$select": "count(1) AS n"}
    if where:
        params["$where"] = where
    try:
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
        return int(rows[0]["n"])
    except (requests.RequestException, ValueError, LookupError) as exc:
        log.warning("  %s: count(1) de conciliación no disponible (%s)", soda_id, exc)
        return None
