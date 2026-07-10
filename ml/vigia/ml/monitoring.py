"""Monitoreo de calidad y salud del modelo (fase 6 de CRISP-ML(Q): operación/monitoreo).

Reúne, sobre los artefactos que ya produce el pipeline, tres señales de "¿sigue siendo
fiable el modelo?" pensadas para operación continua, sin reentrenar:

1. **Frescura de datos** (`freshness`): rezago entre el último mes con datos y hoy, más el
   desglose por categoría (≈ fuente): con solo el máximo GLOBAL, una fuente estancada pasaría
   inadvertida mientras otra siga fresca — las categorías con más de `_LAG_ESTANCADA` meses de
   atraso frente al panel se listan y elevan la señal a amarillo. Datos viejos degradan
   cualquier pronóstico aunque el modelo no cambie.
2. **Deriva de datos** (`data_drift`): PSI (Population Stability Index) de la distribución de
   conteos de delito de los meses recientes vs. el histórico de referencia, más el cambio del
   volumen nacional. Detecta si "el mundo cambió" respecto a lo que el modelo vio al entrenar.
3. **Backtest extendido a 12 meses** (`backtest_horizon`): valida el horizonte LARGO (no solo los
   6 meses del entrenamiento) con el mismo walk-forward sin fuga, y reporta la degradación por paso
   y si el modelo sigue batiendo a la persistencia a 12 meses.
4. **Cobertura de población** (`population_coverage`): el denominador DANE habilita el modelado en
   tasas; si falta, el modelo degrada a conteos en silencio — esta señal lo hace visible.

`health_report` ensambla todo con un semáforo (verde/amarillo/rojo) por señal y global, y lo
persiste en `reports/model_health.json` (auditable). No cambia el modelo: solo observa.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from vigia.config import settings
from vigia.datasets import RESPONSE_CATEGORIES
from vigia.logging import get_logger
from vigia.ml.features import LAGS, feature_columns, make_features
from vigia.ml.forecasting import (
    _as_modeling_target,
    _filter_active_series,
    _has_population,
    _metrics_block,
    _walk_forward,
)

log = get_logger(__name__)

# Umbrales estándar del PSI (literatura de model monitoring): <0.1 estable, 0.1–0.25 deriva
# moderada, ≥0.25 deriva significativa. Se exponen como constantes (calibración explícita).
_PSI_MODERADO = 0.1
_PSI_SIGNIFICATIVO = 0.25
# Rezago de datos (meses) tolerable antes de marcar el tablero como desactualizado.
_LAG_ATENCION = 3
_LAG_CRITICO = 6
# Meses de atraso de una categoría frente al máximo del panel para declararla ESTANCADA. Umbral
# calibrado con el dato real (2026-07): el atraso natural por rezago de publicación y bajo volumen
# llega a ~5 meses (hurto a entidades financieras) — 6 detecta estancamientos genuinos sin falsas
# alarmas.
_LAG_ESTANCADA = 6
# Cobertura mínima del denominador poblacional para considerar sano el modo de tasas.
_MIN_COBERTURA_POBLACION = 95.0


def _delitos(series: pd.DataFrame) -> pd.DataFrame:
    """Solo filas de delito (excluye respuesta institucional), como el detector de anomalías."""
    return series[~series["categoria"].isin(RESPONSE_CATEGORIES)]


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index entre dos muestras (deriva de distribución).

    Los cortes se fijan por cuantiles de la REFERENCIA (sobre log1p, para domar el sesgo de los
    conteos). Un epsilon evita log(0)/división por cero en bins vacíos.
    """
    ref = np.log1p(np.asarray(reference, dtype=float))
    cur = np.log1p(np.asarray(current, dtype=float))
    if ref.size == 0 or cur.size == 0:
        return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_pct = np.histogram(ref, bins=edges)[0] / ref.size
    cur_pct = np.histogram(cur, bins=edges)[0] / cur.size
    eps = 1e-6
    ref_pct = np.clip(ref_pct, eps, None)
    cur_pct = np.clip(cur_pct, eps, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def _estado_psi(value: float) -> str:
    if value >= _PSI_SIGNIFICATIVO:
        return "rojo"
    if value >= _PSI_MODERADO:
        return "amarillo"
    return "verde"


def freshness(series: pd.DataFrame, now: datetime | None = None) -> dict:
    """Rezago entre el último mes con datos y hoy (frescura). Semáforo por meses de rezago.

    Además del máximo GLOBAL, desglosa el último período por categoría (≈ fuente: cada dataset
    aporta una) y lista las ESTANCADAS — las que van más de `_LAG_ESTANCADA` meses detrás del
    panel—, que elevan la señal a amarillo: sin esto, una fuente detenida quedaba invisible
    mientras cualquier otra siguiera fresca.
    """
    now = now or datetime.now(UTC)
    periodos = pd.to_datetime(series["periodo"])
    if periodos.empty:
        return {"periodo_max": None, "lag_meses": None, "estado": "rojo"}
    pmax = periodos.max()
    lag = (now.year - pmax.year) * 12 + (now.month - pmax.month)
    estado = "verde" if lag <= _LAG_ATENCION else "amarillo" if lag <= _LAG_CRITICO else "rojo"
    por_cat = series.assign(_p=periodos).groupby("categoria")["_p"].max()
    atraso = ((pmax.year - por_cat.dt.year) * 12 + (pmax.month - por_cat.dt.month)).astype(int)
    estancadas = [
        {
            "categoria": str(c),
            "periodo_max": por_cat[c].strftime("%Y-%m"),
            "meses_detras_del_panel": int(m),
        }
        for c, m in atraso.sort_values(ascending=False).items()
        if m > _LAG_ESTANCADA
    ]
    if estancadas and estado == "verde":
        estado = "amarillo"
    return {
        "periodo_max": pmax.strftime("%Y-%m"),
        "lag_meses": int(lag),
        "umbral_estancada_meses": _LAG_ESTANCADA,
        "fuentes_estancadas": estancadas,
        "estado": estado,
    }


def data_drift(series: pd.DataFrame, recent_months: int = 6, reference_months: int = 18) -> dict:
    """Deriva de los conteos de delito: PSI (reciente vs referencia) + cambio de volumen nacional.

    La ventana reciente son los últimos `recent_months`; la referencia es una ventana **rolling**
    de los `reference_months` meses INMEDIATAMENTE anteriores (no toda la historia). Una referencia
    rolling mide cambios RECIENTES/súbitos en lugar del crecimiento secular de 20 años, que con una
    referencia de toda la historia mantendría la deriva siempre en rojo. Con `reference_months` muy
    grande (≥ histórico) equivale a comparar contra toda la historia previa.
    """
    delito = _delitos(series)
    periodos = np.sort(pd.to_datetime(delito["periodo"]).dt.to_period("M").unique())
    if len(periodos) <= recent_months + 1:
        return {
            "psi": 0.0,
            "estado": "verde",
            "ventana_meses": recent_months,
            "referencia_meses": reference_months,
            "nota": "histórico insuficiente para evaluar deriva",
        }
    cutoff = periodos[-recent_months]  # inicio de la ventana reciente
    ref_start = periodos[max(0, len(periodos) - recent_months - reference_months)]
    p = pd.to_datetime(delito["periodo"]).dt.to_period("M")
    in_ref = (p >= ref_start) & (p < cutoff)
    ref = delito.loc[in_ref, "cantidad"].to_numpy()
    cur = delito.loc[p >= cutoff, "cantidad"].to_numpy()
    psi_val = round(psi(ref, cur), 4)
    # Cambio de volumen nacional: media mensual reciente vs. referencia (misma ventana rolling).
    vol = delito.assign(_m=p).groupby("_m")["cantidad"].sum()
    vol_ref = float(vol[(vol.index >= ref_start) & (vol.index < cutoff)].mean())
    vol_cur = float(vol[vol.index >= cutoff].mean())
    cambio = round(100 * (vol_cur - vol_ref) / vol_ref, 1) if vol_ref else None
    return {
        "psi": psi_val,
        "estado": _estado_psi(psi_val),
        "ventana_meses": recent_months,
        "referencia_meses": reference_months,
        "volumen_mensual_referencia": round(vol_ref, 1),
        "volumen_mensual_reciente": round(vol_cur, 1),
        "cambio_volumen_pct": cambio,
    }


def backtest_horizon(series: pd.DataFrame, horizon: int = 12, n_splits: int = 2) -> dict | None:
    """Backtest walk-forward extendido al horizonte LARGO (default 12 meses), sin fuga.

    Reaprovecha exactamente el backtest de producción (`forecasting._walk_forward`) con el mismo
    preprocesamiento que `train` (filtro de series activas, modo tasa/conteo, features), pero a un
    horizonte mayor que el de entrenamiento, para vigilar la degradación a largo plazo.
    """
    series = _filter_active_series(series)
    mode = "rate" if _has_population(series) else "count"
    feats = make_features(_as_modeling_target(series, mode)).dropna(subset=[f"lag_{max(LAGS)}"])
    cols = feature_columns(feats)
    if mode == "rate":
        cols = [c for c in cols if c != "tasa_hist"]
    bt = _walk_forward(series, cols, n_splits=n_splits, horizon=horizon, mode=mode)
    if bt is None:
        return None
    step, yt, yp, bl = bt["step"], bt["y_true"], bt["y_pred"], bt["baseline"]
    por_paso = [
        {"paso": int(h), **_metrics_block(yt[step == h], yp[step == h], bl[step == h])}
        for h in range(1, bt["horizon"] + 1)
        if (step == h).any()
    ]
    overall = _metrics_block(yt, yp, bl)
    return {
        "horizon": int(bt["horizon"]),
        "n_origins": int(bt["n_origins"]),
        "mae": overall["mae"],
        "smape": overall["smape"],
        "baseline_mae": overall["baseline_mae"],
        "baseline_smape": overall["baseline_smape"],
        "supera_baseline_mae": bool(overall["mae"] < overall["baseline_mae"]),
        "por_paso": por_paso,
        "estado": "verde" if overall["mae"] < overall["baseline_mae"] else "amarillo",
    }


def population_coverage(series: pd.DataFrame) -> dict:
    """Cobertura del denominador poblacional (DANE) en la serie gold.

    Sin población el modelo degrada CON ELEGANCIA a conteos (modo "count") — no es un fallo,
    pero cambia la calidad del pronóstico y antes ocurría en silencio: esta señal lo declara.
    """
    if "poblacion" not in series.columns or series["poblacion"].isna().all():
        return {
            "disponible": False,
            "cobertura_pct": 0.0,
            "estado": "amarillo",
            "nota": "sin denominador poblacional: el modelo opera en conteos "
            "(vuelva a descargar la fuente `poblacion` y reconstruya gold)",
        }
    cobertura = round(100 * float(series["poblacion"].notna().mean()), 1)
    return {
        "disponible": True,
        "cobertura_pct": cobertura,
        "estado": "verde" if cobertura >= _MIN_COBERTURA_POBLACION else "amarillo",
    }


_PEOR = {"verde": 0, "amarillo": 1, "rojo": 2}


def health_report(
    series: pd.DataFrame,
    horizon: int = 12,
    recent_months: int = 6,
    reference_months: int = 18,
    now: datetime | None = None,
) -> dict:
    """Ensambla las señales de salud + un semáforo global (el peor de las señales)."""
    fresh = freshness(series, now=now)
    drift = data_drift(series, recent_months=recent_months, reference_months=reference_months)
    pob = population_coverage(series)
    bt = backtest_horizon(series, horizon=horizon)
    estados = [fresh["estado"], drift["estado"], pob["estado"]] + ([bt["estado"]] if bt else [])
    global_estado = max(estados, key=lambda e: _PEOR.get(e, 0)) if estados else "verde"
    return {
        "generado_en": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "estado_global": global_estado,
        "frescura": fresh,
        "deriva_datos": drift,
        "poblacion": pob,
        "backtest_extendido": bt,
    }


def write_report(
    series: pd.DataFrame, horizon: int = 12, recent_months: int = 6, reference_months: int = 18
) -> dict:
    """Genera y persiste el reporte de salud en `reports/model_health.json`."""
    import json

    settings.ensure_dirs()
    report = health_report(
        series, horizon=horizon, recent_months=recent_months, reference_months=reference_months
    )
    path = settings.reports_dir / "model_health.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Reporte de salud del modelo escrito en %s (estado=%s)", path, report["estado_global"])
    return report
