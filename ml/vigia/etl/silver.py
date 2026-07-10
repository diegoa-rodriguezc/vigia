"""Capa SILVER — limpieza y unificación de todas las fuentes a un esquema único.

Reto técnico central: las fuentes tienen DOS familias de esquema y DOS formatos
de fecha. Aquí se normalizan a un único modelo de evento delictivo
(ver docs/DATA_DICTIONARY.md#esquema-unificado).
"""

from __future__ import annotations

import json

import pandas as pd

from vigia.config import settings
from vigia.datasets import EVENT_DATASETS, DatasetSpec
from vigia.etl.quality import quality_report
from vigia.logging import get_logger

log = get_logger(__name__)


def _bronze_cap(dataset_id: str) -> tuple[bool, int | None]:
    """Lee del linaje del bronze si la fuente se ingirió con tope (SODA_MAX_ROWS).

    Devuelve `(capped, row_cap)`. Ante meta ausente o ilegible, asume sin tope (False, None):
    el flag es informativo y no debe tumbar la construcción de silver.
    """
    meta_path = settings.bronze_dir / f"{dataset_id}.meta.json"
    if not meta_path.exists():
        return False, None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, None
    return bool(meta.get("capped", False)), meta.get("row_cap")


def _bronze_ingested_at(dataset_id: str) -> str | None:
    """Fecha de ingesta del bronze (linaje). Los meta del bronze están gitignored: elevar la
    fecha al informe de calidad la hace auditable desde el repo. Es una fecha derivada del
    DATO (solo cambia al re-ingerir), no un reloj de pared que ensuciaría el diff del reporte
    en cada ejecución. Ante meta ausente o ilegible devuelve None (informativo)."""
    meta_path = settings.bronze_dir / f"{dataset_id}.meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return meta.get("ingested_at")


# Esquema unificado de salida
UNIFIED_COLUMNS = [
    "fecha",
    "anio",
    "mes",
    "cod_departamento",
    "departamento",
    "cod_municipio",
    "municipio",
    "zona",
    "categoria",
    "arma_medio",
    "sexo",
    "grupo_etario",
    "cantidad",
    "fuente",
    "ingested_at",
]

_PLACEHOLDER = "NO REPORTADO"


def _norm_text(s: pd.Series) -> pd.Series:
    """Normaliza texto: mayúsculas, SIN acentos, sin sufijos `(CT)`, espacios colapsados.

    El stripping de diacríticos es clave: distintas fuentes escriben el mismo municipio
    con/sin tilde (p. ej. 'BOGOTÁ D.C.' vs 'BOGOTA D.C.'), lo que duplicaría territorios.
    """
    out = (
        s.astype("string")
        .str.replace(r"\(.*?\)", "", regex=True)  # quita sufijos como "(CT)"
        .str.strip()
        .str.upper()
        # NFKD + descarte de no-ASCII elimina acentos de forma uniforme
        .str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
    )
    out = out.str.replace(r"\s+", " ", regex=True)
    return out.fillna(_PLACEHOLDER).replace({"": _PLACEHOLDER, "NAN": _PLACEHOLDER})


def _parse_dates(s: pd.Series, fmt: str) -> pd.Series:
    """Interpreta fechas ISO (`2003-01-01T...`) o `dd/mm/yyyy` de forma robusta.

    Garantiza una salida uniforme `datetime64[ns]` SIN zona horaria: a escala real,
    la interpretación mixta puede inferir tz en algunos registros y romper comparaciones.
    """
    raw = s.astype("string").str.strip()
    if fmt == "dmy":
        dt = pd.to_datetime(raw, format="%d/%m/%Y", errors="coerce")
        # Algunos registros pueden venir en ISO aunque la familia sea dmy.
        fallback = pd.to_datetime(raw, errors="coerce", dayfirst=True)
        out = dt.fillna(fallback)
    else:
        out = pd.to_datetime(raw, errors="coerce")
    # Normaliza a tz-naive uniforme (interpreta como UTC y descarta la zona).
    out = pd.to_datetime(out, errors="coerce", utc=True).dt.tz_localize(None)
    return out


def _to_dane5(series: pd.Series, family: str) -> pd.Series:
    """Normaliza el código de municipio a 5 dígitos DANE.

    Familia A: `cod_muni` ya viene en 5 dígitos.
    Familia B: `codigo_dane` viene en 8 dígitos (mmmmm + 3 de centro poblado).
    """
    digits = series.astype("string").str.replace(r"\D", "", regex=True)
    if family == "B":
        digits = digits.str.slice(0, 5)
    code = digits.str.zfill(5).where(digits.str.len().between(1, 5), other=pd.NA)
    # Un código DANE válido nunca tiene '00' como departamento (los dptos van de 05 a 99):
    # esto descarta marcadores como '00000' u '000xx' que la fuente trae con código en blanco.
    return code.where(code.str.slice(0, 2) != "00", other=pd.NA)


def normalize(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    """Convierte un DataFrame crudo (bronze) al esquema unificado de eventos."""
    df = df.copy()
    out = pd.DataFrame(index=df.index)

    out["fecha"] = _parse_dates(df.get("fecha_hecho", pd.Series(index=df.index)), spec.date_format)

    # Códigos / nombres territoriales según familia de esquema
    if spec.schema_family == "A":
        out["cod_municipio"] = _to_dane5(df.get("cod_muni", pd.Series(index=df.index)), "A")
        out["cod_departamento"] = (
            df.get("cod_depto", pd.Series(index=df.index))
            .astype("string")
            .str.replace(r"\D", "", regex=True)
            .str.zfill(2)
        )
    else:  # familia B
        out["cod_municipio"] = _to_dane5(df.get("codigo_dane", pd.Series(index=df.index)), "B")
        out["cod_departamento"] = out["cod_municipio"].str.slice(0, 2)

    out["departamento"] = _norm_text(df.get("departamento", pd.Series(index=df.index)))
    # Algunas fuentes nombran la columna de municipio como `municipio_hecho`.
    municipio_col = df.get("municipio", df.get("municipio_hecho", pd.Series(index=df.index)))
    out["municipio"] = _norm_text(municipio_col)
    out["zona"] = _norm_text(df.get("zona", pd.Series(_PLACEHOLDER, index=df.index)))

    # Categoría: usa la columna de tipo de delito disponible (varía entre fuentes:
    # `tipo_delito` en homicidios/hurto_vehiculos, `tipo_de_hurto` en hurto_modalidades);
    # si ninguna existe, la categoría por defecto de la fuente.
    cat_col = next((c for c in ("tipo_delito", "tipo_de_hurto") if c in df.columns), None)
    if cat_col:
        out["categoria"] = _norm_text(df[cat_col]).str.replace(
            r"^ARTICULO \d+\.\s*", "", regex=True
        )
    else:
        out["categoria"] = spec.categoria

    # Convención canónica única para `categoria`: separador con guion bajo (no espacios).
    # Las fuentes con categoría en texto libre (tipo_delito/tipo_de_hurto) traen vocabularios
    # CONTROLADOS y limpios —verificado contra la API: p. ej. solo HURTO MOTOCICLETAS /
    # HURTO AUTOMOTORES, o SECUESTRO EXTORSIVO / SECUESTRO SIMPLE—, así que NO se requiere un
    # diccionario de sinónimos; basta unificar el separador para que el mismo esquema de
    # nombres aplique a las categorías por defecto (HURTO_PERSONAS) y a las derivadas
    # (HURTO MOTOCICLETAS → HURTO_MOTOCICLETAS). Evita además que una categoría de
    # 'respuesta' derivada de texto no cruce con datasets.RESPONSE_CATEGORIES por el separador.
    out["categoria"] = out["categoria"].astype("string").str.replace(r"\s+", "_", regex=True)

    # Arma / medio (nombre difiere entre familias)
    arma = df.get("arma_medio", df.get("armas_medios", pd.Series(_PLACEHOLDER, index=df.index)))
    out["arma_medio"] = _norm_text(arma)

    # Sexo / género
    sexo = df.get("sexo", df.get("genero", pd.Series(_PLACEHOLDER, index=df.index)))
    out["sexo"] = _norm_text(sexo)

    out["grupo_etario"] = _norm_text(
        df.get("grupo_etario", pd.Series(_PLACEHOLDER, index=df.index))
    )

    out["cantidad"] = (
        pd.to_numeric(df.get("cantidad", 1), errors="coerce")
        .fillna(1)
        .clip(lower=0)
        .astype("int64")
    )

    out["fuente"] = spec.id
    out["ingested_at"] = pd.Timestamp.utcnow()

    # Descarte de filas sin fecha válida o sin código de municipio (no localizables
    # para análisis espacial ni para las tablas que expone el backend).
    out = out[out["fecha"].notna() & out["cod_municipio"].notna()].copy()
    out["anio"] = out["fecha"].dt.year.astype("int64")
    out["mes"] = out["fecha"].dt.month.astype("int64")
    # descarta cantidades nulas y fechas absurdas (antes de 1990 o futuras lejanas)
    out = out[(out["anio"] >= 1990) & (out["cantidad"] > 0)]

    return out[UNIFIED_COLUMNS].reset_index(drop=True)


def _apply_official_names(eventos: pd.DataFrame) -> pd.DataFrame:
    """Reemplaza municipio/departamento por los nombres oficiales DANE (DIVIPOLA).

    Cruce por código DANE de municipio. Donde DIVIPOLA no tiene el código, se conserva
    el nombre normalizado de la fuente. Si DIVIPOLA no está disponible, no altera nada.
    """
    from vigia.etl.divipola import load_municipios

    try:
        ref = load_municipios()
    except RuntimeError as exc:
        log.warning("Nombres oficiales no aplicados (%s)", exc)
        return eventos

    ref = ref[["cod_municipio", "municipio", "departamento", "cod_departamento"]].rename(
        columns={
            "municipio": "_muni_ofi",
            "departamento": "_dep_ofi",
            "cod_departamento": "_coddep_ofi",
        }
    )
    merged = eventos.merge(ref, on="cod_municipio", how="left")
    cobertura = merged["_muni_ofi"].notna().mean()
    for col, ofi in (
        ("municipio", "_muni_ofi"),
        ("departamento", "_dep_ofi"),
        ("cod_departamento", "_coddep_ofi"),
    ):
        merged[col] = merged[ofi].fillna(merged[col])
    merged = merged.drop(columns=["_muni_ofi", "_dep_ofi", "_coddep_ofi"])
    log.info("Nombres oficiales DIVIPOLA aplicados a %.1f%% de los eventos", 100 * cobertura)
    return merged


def build_silver(only: list[str] | None = None) -> pd.DataFrame:
    """Lee bronze, normaliza cada fuente de eventos y consolida `silver/eventos.parquet`."""
    settings.ensure_dirs()
    frames: list[pd.DataFrame] = []
    procedencia: dict[str, dict[str, int | float]] = {}
    specs = [s for s in EVENT_DATASETS.values() if only is None or s.id in only]

    for spec in specs:
        src = settings.bronze_dir / f"{spec.id}.parquet"
        if not src.exists():
            log.warning(
                "Sin datos de la fuente %s en la capa bronze (%s); fuente omitida",
                spec.id,
                src.name,
            )
            continue
        raw = pd.read_parquet(src)
        if raw.empty:
            continue
        norm = normalize(raw, spec)
        log.info("Normalizado %s: %d filas -> %d válidas", spec.id, len(raw), len(norm))
        # Conciliación crudo→silver auditable desde el repo (va al informe de calidad):
        # los descartes provienen SOLO de fecha/código de municipio inválidos (ver normalize).
        procedencia[spec.id] = {
            "filas_crudas": int(len(raw)),
            "filas_validas": int(len(norm)),
            "descartadas_pct": round(100 * (1 - len(norm) / len(raw)), 2),
        }
        # Fecha de ingesta del bronze (linaje auditable desde el repo; se omite si el meta falta).
        ingerido = _bronze_ingested_at(spec.id)
        if ingerido:
            procedencia[spec.id]["ingerido_el"] = ingerido
        # Si el bronze se truncó por SODA_MAX_ROWS, `filas_crudas` NO es el volumen del portal
        # sino el recortado: dejarlo explícito para que el reporte de calidad no mienta. Solo se
        # inyecta cuando hubo tope; así una ejecución SIN tope produce la procedencia idéntica.
        capped, row_cap = _bronze_cap(spec.id)
        if capped:
            procedencia[spec.id]["truncado"] = True
            procedencia[spec.id]["row_cap"] = row_cap
        frames.append(norm)

    if not frames:
        raise RuntimeError("No hay datos en bronze. Ejecute primero `vigia ingest`.")

    eventos = pd.concat(frames, ignore_index=True)
    eventos = _apply_official_names(eventos)
    # AQUÍ NO SE ELIMINAN FILAS REPETIDAS (a propósito): el grano de silver es el del publicador
    # y una fila idéntica a otra es un hecho DISTINTO con atributos gruesos, no un duplicado. Un
    # `drop_duplicates()` global llegó a borrar ~30 % de las filas (homicidios −21 %,
    # capturas −66 %) y deflactaba todas las cifras. Evidencia de que las repetidas son
    # legítimas: (1) las fuentes que el publicador entrega PRE-AGREGADAS (`cantidad`>1:
    # hurto_personas, hurto_vehiculos, violencia_intrafamiliar) traen 0 filas repetidas — la
    # repetición solo existe donde el grano es evento (`cantidad`≈1) y el esquema es estrecho;
    # (2) la serie anual de homicidios con las repetidas conservadas reproduce la cifra oficial
    # de la Policía (p. ej. 2023 ≈ 13,6 mil) y al eliminarlas queda 15-30 % por debajo; (3) la
    # paginación SODA es estable (`$order=:id`) y no reintroduce filas. No restaurar el borrado.

    out = settings.silver_dir / "eventos.parquet"
    eventos.to_parquet(out, index=False)
    log.info("Capa silver consolidada: %d eventos -> %s", len(eventos), out)

    # Informe de calidad de datos (QA de CRISP-ML(Q))
    report = quality_report(eventos, procedencia=procedencia)
    (settings.reports_dir / "silver_quality.json").write_text(report, encoding="utf-8")
    return eventos
