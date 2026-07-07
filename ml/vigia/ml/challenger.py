"""Champion vs challenger: ¿una red neuronal supera al gradient boosting?

El modelo en producción (seleccionado) es un `HistGradientBoostingRegressor` global. Este módulo
mide un **challenger neuronal** —un perceptrón multicapa (MLP)— bajo EXACTAMENTE el mismo
backtest walk-forward recursivo sin fuga, para decidir con evidencia (no por intuición) si
vale la pena cambiar de familia de modelo. Es una herramienta de EVALUACIÓN: no toca el
artefacto en producción; reentrenar/cablear el ganador es una decisión aparte y explícita.

El MLP exige escalado de features (a diferencia de los árboles), así que el challenger es un
`Pipeline(StandardScaler, MLPRegressor)`. Se mantiene en scikit-learn (sin Torch/TF): una red
pequeña basta para la comparación y conserva la reproducibilidad y la huella ligera del proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from vigia.config import settings
from vigia.logging import get_logger
from vigia.ml.features import LAGS, feature_columns, make_features
from vigia.ml.forecasting import (
    _as_modeling_target,
    _filter_active_series,
    _has_population,
    _smape,
    _walk_forward,
)

log = get_logger(__name__)

# Arquitectura del challenger neuronal. Pequeña a propósito: dos capas ocultas; `early_stopping`
# corta cuando deja de mejorar (evita sobreajuste y acota el tiempo). Semilla fija (reproducible).
_MLP_PARAMS: dict = {
    "hidden_layer_sizes": (64, 32),
    "activation": "relu",
    "alpha": 1e-3,
    "learning_rate_init": 0.01,
    "max_iter": 300,
    "early_stopping": True,
    "n_iter_no_change": 10,
}


def _new_mlp() -> Pipeline:
    """MLP con escalado previo (las redes son sensibles a la escala de las features)."""
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("mlp", MLPRegressor(random_state=settings.seed, **_MLP_PARAMS)),
        ]
    )


@dataclass
class Comparison:
    champion: dict
    challenger: dict
    verdict: str


def _scores(bt: dict) -> dict:
    """MAE/sMAPE a 1 paso y multipaso a partir de los arrays del backtest."""
    step, yt, yp = bt["step"], bt["y_true"], bt["y_pred"]
    one = step == 1
    return {
        "n_origins": int(bt["n_origins"]),
        "horizon": int(bt["horizon"]),
        "mae_1paso": round(float(mean_absolute_error(yt[one], yp[one])), 4) if one.any() else None,
        "smape_1paso": round(_smape(yt[one], yp[one]), 2) if one.any() else None,
        "mae_multipaso": round(float(mean_absolute_error(yt, yp)), 4),
        "smape_multipaso": round(_smape(yt, yp), 2),
    }


def compare(series: pd.DataFrame, test_months: int = 6, n_splits: int = 3) -> Comparison:
    """Compara el ganador (HGB) contra el challenger (MLP) bajo el mismo backtest sin fuga.

    Replica el preprocesamiento de `forecasting.train` (filtro de series activas, modo
    tasa/conteo y columnas de features) para que la única diferencia entre ambos sea la familia
    del estimador. Devuelve métricas paralelas y un veredicto.
    """
    series = _filter_active_series(series)
    mode = "rate" if _has_population(series) else "count"
    feats = make_features(_as_modeling_target(series, mode)).dropna(subset=[f"lag_{max(LAGS)}"])
    cols = feature_columns(feats)
    if mode == "rate":
        cols = [c for c in cols if c != "tasa_hist"]

    log.info("Champion (HGB) vs challenger (MLP) — modo=%s, %d features", mode, len(cols))
    bt_champ = _walk_forward(series, cols, n_splits=n_splits, horizon=test_months, mode=mode)
    bt_chall = _walk_forward(
        series, cols, n_splits=n_splits, horizon=test_months, mode=mode, make_estimator=_new_mlp
    )
    if bt_champ is None or bt_chall is None:
        raise RuntimeError("Datos insuficientes para el backtest comparativo.")

    champ, chall = _scores(bt_champ), _scores(bt_chall)
    # Veredicto por el MAE multipaso, la métrica del horizonte que se entrega. Margen relativo.
    margen = (champ["mae_multipaso"] - chall["mae_multipaso"]) / max(champ["mae_multipaso"], 1e-9)
    if margen > 0.01:
        verdict = f"El challenger MLP mejora el MAE multipaso {margen * 100:.1f}% — evaluar cambio."
    elif margen < -0.01:
        verdict = (
            f"El champion HGB mantiene la ventaja ({-margen * 100:.1f}% mejor MAE multipaso) — "
            "no se justifica cambiar de modelo."
        )
    else:
        verdict = (
            "Empate técnico (<1% de MAE multipaso) — se conserva el champion HGB por simplicidad."
        )
    log.info("Veredicto champion/challenger: %s", verdict)
    return Comparison(champion=champ, challenger=chall, verdict=verdict)


def write_report(series: pd.DataFrame, test_months: int = 6, n_splits: int = 3) -> dict:
    """Ejecuta la comparación y la persiste en `reports/challenger.json` (reproducible)."""
    import json

    cmp = compare(series, test_months=test_months, n_splits=n_splits)
    settings.ensure_dirs()
    report = {
        "champion": {"modelo": "HistGradientBoostingRegressor", **cmp.champion},
        "challenger": {"modelo": "MLPRegressor", "arquitectura": _MLP_PARAMS, **cmp.challenger},
        "veredicto": cmp.verdict,
    }
    path = settings.reports_dir / "challenger.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Reporte challenger guardado en %s", path)
    return report
