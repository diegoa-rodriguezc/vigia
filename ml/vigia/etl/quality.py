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

    silver convierte el tipo del texto con ``.astype("string")`` (``StringDtype``), que **no**
    es ``object``: filtrar solo por ``dtype == object`` saltaba todas esas columnas y dejaba
    ``placeholders_pct`` vacío. Aquí se contemplan los tres dtypes textuales posibles.
    """
    return (
        s.dtype == object
        or pd.api.types.is_string_dtype(s.dtype)
        or isinstance(s.dtype, pd.CategoricalDtype)
    )


def quality_report(df: pd.DataFrame, procedencia: dict[str, dict] | None = None) -> str:
    """Construye un informe de calidad serializado en JSON.

    `procedencia` (opcional) es la conciliación crudo→silver por fuente que aporta
    `build_silver` ({fuente: {filas_crudas, filas_validas, descartadas_pct}}), para que la
    diferencia entre el volumen del portal y el de silver sea auditable sin correr el pipeline.
    """
    # % de valores que son el marcador "NO REPORTADO" en cada campo de texto donde aparece.
    # `completitud_pct` da 100% por construcción (silver imputa el marcador en vez de dejar
    # nulos); este desglose muestra el subregistro REAL por campo, sin maquillarlo.
    placeholders_pct: dict[str, float] = {}
    for col in df.columns:
        if not _is_text(df[col]):
            continue
        # `==` sobre StringDtype devuelve un boolean nullable: NA (valor ausente) cuenta como
        # "no es marcador", de modo que el % se calcula sobre TODAS las filas, no las no-nulas.
        is_placeholder = (df[col] == _PLACEHOLDER).fillna(False)
        if is_placeholder.any():
            placeholders_pct[col] = round(100 * is_placeholder.mean(), 2)
    report: dict = {
        "filas": int(len(df)),
        "fuentes": df["fuente"].value_counts().to_dict(),
        # Conciliación crudo→silver por fuente (la aporta build_silver). Silver NO elimina
        # filas repetidas: en las fuentes a grano de evento las filas idénticas son hechos
        # distintos con atributos gruesos (las fuentes pre-agregadas no traen filas repetidas y
        # la serie de homicidios con las repetidas conservadas reproduce la cifra oficial anual
        # de la Policía).
        "procedencia": procedencia or {},
        "nota_procedencia": (
            "filas_crudas → filas_validas por fuente; los descartes provienen solo de fecha o "
            "código de municipio inválidos. No se eliminan filas repetidas: una fila idéntica "
            "a otra es un hecho distinto con atributos gruesos, no un duplicado del publicador. "
            "`ingerido_el` es la fecha de ingesta del bronze de cada fuente (linaje auditable "
            "sin correr el pipeline; los meta del bronze no se versionan)."
        ),
        "rango_fechas": {
            "min": str(df["fecha"].min().date()) if len(df) else None,
            "max": str(df["fecha"].max().date()) if len(df) else None,
        },
        "completitud_pct": {col: round(100 * df[col].notna().mean(), 2) for col in df.columns},
        "nota_completitud": (
            "completitud_pct es 100% por construcción: silver imputa el marcador "
            f"'{_PLACEHOLDER}' en los campos de texto ausentes en vez de dejar nulos. "
            "Ver placeholders_pct para el % real de no reportados por campo."
        ),
        "placeholders_pct": placeholders_pct,
        "municipios_unicos": int(df["cod_municipio"].nunique()),
        "categorias": sorted(df["categoria"].dropna().unique().tolist())[:50],
        "total_hechos": int(df["cantidad"].sum()),
        "alertas": _checks(df) + _truncation_alerts(procedencia),
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def _truncation_alerts(procedencia: dict[str, dict] | None) -> list[str]:
    """Alertas por fuentes truncadas en la ingesta (SODA_MAX_ROWS).

    `build_silver` marca `truncado`/`row_cap` en la procedencia de la fuente cuyo bronze se cortó
    en el tope. Se eleva a alerta VISIBLE para que una ejecución parcial no se lea como completa.
    """
    alerts: list[str] = []
    for fuente, p in (procedencia or {}).items():
        if p.get("truncado"):
            cap = p.get("row_cap")
            alerts.append(
                f"Fuente '{fuente}' ingerida con tope SODA_MAX_ROWS={cap}: volumen posiblemente "
                "PARCIAL; los conteos de esta fuente y sus derivados NO representan el total real."
            )
    return alerts


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
