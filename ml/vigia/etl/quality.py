"""Controles de calidad declarativos (QA de CRISP-ML(Q)).

Genera un informe de calidad sobre la capa silver: completitud, dominios,
rangos temporales y volúmenes. Se persiste en `reports/silver_quality.json`.
"""

from __future__ import annotations

import json

import pandas as pd

# Literal con el que `silver._clean_text` rellena los campos de texto ausentes/vacíos.
# Se mide su frecuencia aparte para no sobrevender el 100% de completitud estructural.
_PLACEHOLDER = "NO REPORTADO"


def _is_text(s: pd.Series) -> bool:
    """¿Es una columna de texto? (object, pandas ``StringDtype`` o categórica).

    silver convierte el tipo de los campos de texto con ``.astype("string")`` (``StringDtype``), que **no**
    es ``object``: filtrar solo por ``dtype == object`` saltaba todas esas columnas y dejaba
    ``placeholders_pct`` vacío. Aquí se contemplan los tres dtypes textuales posibles.
    """
    return (
        s.dtype == object
        or pd.api.types.is_string_dtype(s.dtype)
        or isinstance(s.dtype, pd.CategoricalDtype)
    )


def quality_report(df: pd.DataFrame) -> str:
    """Construye un informe de calidad serializado en JSON."""
    # % de valores que son el placeholder "NO REPORTADO" en cada campo de texto donde aparece.
    # `completitud_pct` da 100% por construcción (silver imputa el placeholder en vez de dejar
    # nulos); este desglose muestra el subregistro REAL por campo, sin maquillarlo.
    placeholders_pct: dict[str, float] = {}
    for col in df.columns:
        if not _is_text(df[col]):
            continue
        # `==` sobre StringDtype devuelve un boolean nullable: NA (valor ausente) cuenta como
        # "no es placeholder", de modo que el % se calcula sobre TODAS las filas, no las no-nulas.
        is_placeholder = (df[col] == _PLACEHOLDER).fillna(False)
        if is_placeholder.any():
            placeholders_pct[col] = round(100 * is_placeholder.mean(), 2)
    report: dict = {
        "filas": int(len(df)),
        "fuentes": df["fuente"].value_counts().to_dict(),
        "rango_fechas": {
            "min": str(df["fecha"].min().date()) if len(df) else None,
            "max": str(df["fecha"].max().date()) if len(df) else None,
        },
        "completitud_pct": {col: round(100 * df[col].notna().mean(), 2) for col in df.columns},
        "nota_completitud": (
            "completitud_pct es 100% por construcción: silver imputa el placeholder "
            f"'{_PLACEHOLDER}' en los campos de texto ausentes en vez de dejar nulos. "
            "Ver placeholders_pct para el % real de no reportados por campo."
        ),
        "placeholders_pct": placeholders_pct,
        "municipios_unicos": int(df["cod_municipio"].nunique()),
        "categorias": sorted(df["categoria"].dropna().unique().tolist())[:50],
        "total_hechos": int(df["cantidad"].sum()),
        "alertas": _checks(df),
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def _checks(df: pd.DataFrame) -> list[str]:
    """Reglas de validación; cada incumplimiento agrega una alerta al informe."""
    alerts: list[str] = []
    if df["cod_municipio"].isna().any():
        n = int(df["cod_municipio"].isna().sum())
        alerts.append(f"{n} filas sin código de municipio")
    if (df["cantidad"] <= 0).any():
        alerts.append("Existen cantidades <= 0 (deberían haberse filtrado)")
    if df["fecha"].isna().any():
        alerts.append("Existen fechas nulas en silver")
    future = df["fecha"] > pd.Timestamp.now()  # tz-naive, coherente con `fecha`
    if future.any():
        alerts.append(f"{int(future.sum())} eventos con fecha futura")
    return alerts
