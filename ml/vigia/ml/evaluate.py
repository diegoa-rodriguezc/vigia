"""Evaluación del modelo y reporte reproducible (fase 4 de CRISP-ML(Q)).

Persiste en `reports/model_report.json` las métricas de backtesting y las
estadísticas del conjunto modelado, de modo que las cifras de la bitácora
metodológica (`docs/CRISP-ML-Q.md`) se **regeneren** en cada ejecución y sean
auditables por el jurado, en lugar de vivir escritas a mano en el documento.
"""

from __future__ import annotations

import json

import pandas as pd

from vigia.config import settings
from vigia.logging import get_logger
from vigia.ml.features import KEY
from vigia.ml.forecasting import ForecastModel, _filter_active_series

log = get_logger(__name__)

REPORT_PATH = settings.reports_dir / "model_report.json"


def _series_stats(series: pd.DataFrame, min_nonzero: int = 12) -> dict:
    """Estadísticas del universo modelado (tras filtrar series con poca señal)."""
    modeled = _filter_active_series(series, min_nonzero=min_nonzero)
    empty = modeled.empty
    periodo = (
        pd.to_datetime(modeled["periodo"]) if not empty else pd.Series([], dtype="datetime64[ns]")
    )
    return {
        "series_modeladas": int(modeled.groupby(KEY, dropna=False).ngroups) if not empty else 0,
        "municipios_modelados": int(modeled["cod_municipio"].nunique()),
        "categorias_modeladas": int(modeled["categoria"].nunique()),
        "hechos_modelados": int(modeled["cantidad"].sum()),
        "periodo_min": periodo.min().strftime("%Y-%m") if len(periodo) else None,
        "periodo_max": periodo.max().strftime("%Y-%m") if len(periodo) else None,
        "min_nonzero": min_nonzero,
    }


def _anomaly_stats(series: pd.DataFrame | None = None, min_history: int = 18, path=None) -> dict:
    """Conteo de anomalías persistidas en gold + su TASA respecto al universo evaluado.

    Reportar la tasa (y alertas por serie) evita malinterpretar el total absoluto: el
    detector exige consenso de dos señales y solo picos al alza, así que la tasa real queda
    muy por debajo de `contamination` y es operativamente manejable (no son alertas
    simultáneas, sino un catálogo histórico desde 2003).
    """
    path = path or (settings.gold_dir / "anomalias.parquet")
    if not path.exists():
        return {"total": 0, "alta": 0, "media": 0}
    df = pd.read_parquet(path)
    sev = df["severidad"].value_counts() if "severidad" in df else pd.Series(dtype=int)
    stats = {
        "total": int(len(df)),
        "alta": int(sev.get("ALTA", 0)),
        "media": int(sev.get("MEDIA", 0)),
    }
    if series is not None and not series.empty:
        from vigia.datasets import RESPONSE_CATEGORIES

        delito = series[~series["categoria"].isin(RESPONSE_CATEGORIES)]
        n = delito.groupby(KEY)["cantidad"].transform("size")
        evaluable = delito[n >= min_history]
        universo = int(len(evaluable))  # meses-serie de delito que el detector evalúa
        series_eval = int(evaluable.groupby(KEY, dropna=False).ngroups)
        con_alerta = (
            int(df.groupby(KEY, dropna=False).ngroups) if set(KEY).issubset(df.columns) else 0
        )
        stats.update(
            universo_meses_serie=universo,
            tasa_alertas_pct=round(100 * stats["total"] / universo, 3) if universo else None,
            series_evaluadas=series_eval,
            series_con_alerta=con_alerta,
            alertas_por_serie=round(stats["total"] / series_eval, 2) if series_eval else None,
        )
    return stats


def build_model_report(series: pd.DataFrame, model: ForecastModel) -> dict:
    """Construye el reporte de evaluación a partir de la serie y el modelo entrenado."""
    metrics = dict(model.metrics)
    inf = float("inf")
    multipaso = metrics.get("multipaso", {})
    return {
        "trained_at": model.trained_at,
        "seed": settings.seed,
        "features": model.feature_cols,
        "metricas_backtest": metrics,
        # Veredicto honesto y matizado: el modelo gana en sMAPE (1 paso y horizonte completo);
        # en MAE la persistencia es casi imbatible en el tercil de volumen ínfimo (ver
        # `por_volumen`), donde el error absoluto es diminuto y domina el agregado.
        "supera_linea_base_smape": bool(
            metrics.get("smape", inf) < metrics.get("baseline_smape", inf)
        ),
        "supera_linea_base_mae": bool(metrics.get("mae", inf) < metrics.get("baseline_mae", inf)),
        "supera_linea_base_smape_multipaso": bool(
            multipaso.get("smape", inf) < multipaso.get("baseline_smape", inf)
        ),
        # Vara ESTACIONAL (mismo mes del año anterior), más exigente que la persistencia. None si
        # el backtest no la reportó (p. ej. modelo de prueba sin línea base estacional).
        "supera_linea_base_estacional_mae": (
            bool(metrics["mae"] < metrics["baseline_estacional_mae"])
            if "mae" in metrics and "baseline_estacional_mae" in metrics
            else None
        ),
        "supera_linea_base_estacional_mae_multipaso": (
            bool(multipaso["mae"] < multipaso["baseline_estacional_mae"])
            if "mae" in multipaso and "baseline_estacional_mae" in multipaso
            else None
        ),
        "interpretabilidad": {
            "metodo": "permutation_importance",
            "scoring": "neg_mean_absolute_error",
            "nota": "caída de MAE al barajar cada feature, sobre una muestra del conjunto modelado",
            "features": model.importancias,
        },
        "universo_modelado": _series_stats(series),
        "anomalias": _anomaly_stats(series),
    }


def write_model_report(series: pd.DataFrame, model: ForecastModel) -> dict:
    """Genera y persiste el reporte en `reports/model_report.json`. Devuelve el dict."""
    settings.ensure_dirs()
    report = build_model_report(series, model)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Reporte de modelo escrito en %s", REPORT_PATH)
    return report
