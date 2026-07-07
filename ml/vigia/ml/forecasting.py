"""Pronóstico de criminalidad por municipio y mes (modelo global).

Un único `HistGradientBoostingRegressor` se entrena sobre TODAS las series
`municipio × categoria` usando features de rezago/estacionalidad. Ventajas:
robusto, sin dependencias pesadas, comparte señal entre territorios (útil para
municipios con pocos datos) y es reproducible con semilla fija.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error

from vigia.config import settings
from vigia.logging import get_logger
from vigia.ml.features import KEY, LAGS, TARGET, feature_columns, make_features

log = get_logger(__name__)

MODEL_PATH = settings.models_dir / "forecaster.joblib"
# Metadatos del artefacto (versión de sklearn que lo serializó): un joblib NO es portable entre
# versiones, y sin esto el error de carga dice qué pasó pero no QUIÉN escribió el modelo.
META_PATH = MODEL_PATH.with_suffix(".meta.json")


@dataclass
class ForecastModel:
    """Modelo entrenado + metadatos para inferencia recursiva."""

    estimator: HistGradientBoostingRegressor
    feature_cols: list[str]
    last_periodo: pd.Timestamp
    metrics: dict = field(default_factory=dict)
    trained_at: str = ""
    resid_dispersion: float = 0.0  # dispersión cuasi-Poisson del backtest (para intervalos)
    importancias: list = field(default_factory=list)  # interpretabilidad (permutation importance)
    # Escala de la banda de incertidumbre, CALIBRADA empíricamente (estilo conformal) sobre los
    # residuos out-of-fold del backtest para que la cobertura iguale el nivel nominal (80%). Antes
    # se asumía el cuantil normal (1.2816), que con la dispersión cuasi-Poisson daba una banda
    # demasiado ANCHA (cobertura ~94%). Default = cuantil normal para modelos antiguos sin el campo.
    pi_scale: float = 1.2816
    # Variable que modela el estimador: "rate" (hechos por 100.000 hab.) cuando hay población, o
    # "count" (conteos) si no. El pronóstico SIEMPRE se entrega en conteos: en modo "rate" se
    # convierte multiplicando por la población. Modelar tasas iguala la escala entre municipios
    # (Bogotá vs uno pequeño) y mejora MAE y sMAPE frente a modelar conteos (ver bitácora).
    target_mode: str = "count"


# Cuantil normal para ~80% de cobertura central (banda ± z·σ). El concurso valora el
# manejo explícito de la incertidumbre en la analítica predictiva.
_PI_Z = 1.2816
_PI_LEVEL = 80

# Tasa expresada por 100.000 habitantes (convención epidemiológica estándar).
RATE_SCALE = 100_000.0

# Peso del modelo en la predicción ENTREGADA (resto: persistencia del último valor observado).
# El modelo global gana en volumen medio pero puede sobre-extrapolar en mega-ciudades (un error
# de tasa pequeño × población enorme = gran error de conteo); mezclar con persistencia —fuerte
# en alto volumen— doma esa sobreestimación SIN perder la ventaja en medio. Calibrado por
# backtest: 0.7 bate a la línea base en MAE (1 paso y multipaso), sMAPE multipaso y el tercil
# alto (ver bitácora).
_BLEND_W = 0.7


def _pop_series(df: pd.DataFrame) -> pd.Series:
    """Población numérica con piso 1 (evita división por cero al pasar a tasa)."""
    return pd.to_numeric(df["poblacion"], errors="coerce").clip(lower=1.0)


def _has_population(series: pd.DataFrame) -> bool:
    """¿La serie trae población utilizable para modelar tasas?"""
    return (
        "poblacion" in series.columns
        and pd.to_numeric(series["poblacion"], errors="coerce").gt(0).any()
    )


def _as_modeling_target(series: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Copia de la serie cuyo TARGET es la variable a modelar (conteo o tasa).

    En modo "rate" se sustituye el conteo por su tasa por 100.000 habitantes para que las
    features de rezago/medias se computen sobre la tasa; la población se conserva para
    reconvertir la predicción a conteo.
    """
    if mode != "rate":
        return series
    d = series.copy()
    d[TARGET] = d[TARGET].astype(float) / _pop_series(d) * RATE_SCALE
    return d


def _smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom > 0
    if not mask.any():
        return 0.0
    return float(100 * np.mean(2 * np.abs(y_pred - y_true)[mask] / denom[mask]))


def _filter_active_series(series: pd.DataFrame, min_nonzero: int = 12) -> pd.DataFrame:
    """Conserva solo las series con suficiente historia no nula.

    El pronóstico aporta valor donde hay señal recurrente; entrenar/evaluar sobre
    series casi vacías (conteos minúsculos esporádicos) distorsiona las métricas y
    favorece artificialmente a la línea base ingenua.
    """
    nonzero = series.assign(_nz=series["cantidad"] > 0).groupby(KEY)["_nz"].transform("sum")
    keep = nonzero >= min_nonzero
    return series[keep].copy()


# Hiperparámetros del estimador, CONFIRMADOS por una búsqueda con CV TEMPORAL (walk-forward,
# sin fuga) que puntuó 8 configuraciones por el MAE multipaso de la predicción entregada (ver
# bitácora Iteración 9 y docs/CRISP-ML-Q.md): todas cayeron dentro del 1.4% y la mejor alternativa
# solo daba −0.8% de MAE a costa de 2× el tiempo de entrenamiento → estos defaults quedan como
# óptimo práctico. NO ajustar con k-fold aleatorio: barajaría el tiempo y filtraría el futuro
# (métricas engañosamente buenas).
_HGB_PARAMS: dict = {
    "max_iter": 400,
    "learning_rate": 0.05,
    "max_depth": 8,
    "l2_regularization": 1.0,
}


def _new_estimator(overrides: dict | None = None) -> HistGradientBoostingRegressor:
    """Estimador con la configuración estándar (misma semilla para reproducibilidad).

    `overrides` permite inyectar hiperparámetros candidatos durante la búsqueda (HPO,
    Hyperparameter Optimization) sin tocar los de producción.

    Nota empírica (bitácora en docs/CRISP-ML-Q.md): `loss="poisson"` extrapola por su enlace
    logarítmico y dispara el MAE en la recursión multipaso —de forma CATASTRÓFICA sobre conteos
    (errores ~1e73), confirmado al re-probarlo incluso con población—. La pérdida cuadrática es
    estable; la escala de los conteos se aborda modelando TASAS (no cambiando la pérdida).
    """
    params = {**_HGB_PARAMS, **(overrides or {})}
    return HistGradientBoostingRegressor(random_state=settings.seed, **params)


def _mase(y_true: np.ndarray, y_pred: np.ndarray, scale: np.ndarray) -> float | None:
    """MASE (Hyndman): MAE escalado por el MAE ingenuo 1-paso *in-sample* de CADA serie.

    `scale` es, por punto, el MAE de la persistencia dentro de la muestra de entrenamiento de
    su serie (media de |yₜ−yₜ₋₁|). **MASE < 1 ⇒ el pronóstico fuera de muestra bate al naive
    dentro de muestra**; es adimensional y comparable entre series de cualquier volumen. A
    diferencia del sMAPE, NO se degenera sobre conteos casi nulos (0/1) —donde el sMAPE dispara
    a >100% y deja de ser interpretable—, por eso es la métrica de cabecera. Se ignoran los
    puntos con `scale` nula/indefinida (serie de historia constante).
    """
    scale = np.asarray(scale, dtype=float)
    mask = np.isfinite(scale) & (scale > 0)
    if not mask.any():
        return None
    err = np.abs(np.asarray(y_pred, dtype=float) - np.asarray(y_true, dtype=float))
    return float(np.mean(err[mask] / scale[mask]))


def _metrics_block(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    baseline: np.ndarray,
    baseline_season: np.ndarray | None = None,
    scale: np.ndarray | None = None,
) -> dict:
    """Error del modelo y de las líneas base sobre el mismo conjunto.

    Además de la persistencia (naive), reporta —cuando se aportan— la **baseline estacional**
    (mismo mes del año anterior, una vara más exigente en series con estacionalidad) y el
    **MASE** del modelo y de la persistencia (métrica escalada, interpretable en conteos dispersos).
    """
    blk = {
        "n": int(len(y_true)),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "smape": round(_smape(y_true, y_pred), 2),
        "baseline_mae": round(float(mean_absolute_error(y_true, baseline)), 4),
        "baseline_smape": round(_smape(y_true, baseline), 2),
    }
    if baseline_season is not None and len(baseline_season):
        blk["baseline_estacional_mae"] = round(
            float(mean_absolute_error(y_true, baseline_season)), 4
        )
        blk["baseline_estacional_smape"] = round(_smape(y_true, baseline_season), 2)
    if scale is not None and len(scale):
        m = _mase(y_true, y_pred, scale)
        if m is not None:
            blk["mase"] = round(m, 4)
        mb = _mase(y_true, baseline, scale)
        if mb is not None:
            blk["baseline_mase"] = round(mb, 4)
    return blk


def _stratify_by_volume(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    baseline: np.ndarray,
    vol: np.ndarray,
    baseline_season: np.ndarray | None = None,
    scale: np.ndarray | None = None,
) -> list[dict]:
    """Desglosa el error a 1 paso por TERCIL de volumen de la serie (media histórica).

    Reconcilia la aparente "derrota" en MAE frente a la línea base: la persistencia
    (repetir el último mes) es casi imbatible en series de volumen ínfimo (conteos
    minúsculos y esporádicos, donde el MAE absoluto es diminuto y domina el agregado),
    mientras que el modelo aporta valor donde hay señal recurrente —volumen medio/alto—,
    que es justo donde la planeación preventiva importa. El agregado global mezcla ambos
    regímenes; este desglose lo separa.
    """
    if len(vol) == 0:
        return []
    q1, q2 = (float(x) for x in np.quantile(vol, [1 / 3, 2 / 3]))
    estratos = [
        ("bajo", vol <= q1, f"≤{q1:.1f}"),
        ("medio", (vol > q1) & (vol <= q2), f"{q1:.1f}–{q2:.1f}"),
        ("alto", vol > q2, f">{q2:.1f}"),
    ]
    out: list[dict] = []
    for nombre, mask, rango in estratos:
        if not mask.any():
            continue
        blk = _metrics_block(
            y_true[mask],
            y_pred[mask],
            baseline[mask],
            baseline_season=None if baseline_season is None else baseline_season[mask],
            scale=None if scale is None else scale[mask],
        )
        blk.update(
            estrato=nombre,
            rango_volumen_mensual=rango,
            gana_modelo=bool(
                blk["smape"] < blk["baseline_smape"] and blk["mae"] <= blk["baseline_mae"]
            ),
        )
        out.append(blk)
    return out


def _walk_forward(
    series: pd.DataFrame,
    cols: list[str],
    n_splits: int,
    horizon: int,
    min_train: int = 50,
    mode: str = "count",
    hgb_params: dict | None = None,
    make_estimator=None,
):
    """Backtest walk-forward RECURSIVO multi-paso (rolling origin), sin fuga de datos.

    Para cada uno de los últimos `n_splits` orígenes temporales se entrena un estimador
    SOLO con el pasado y se pronostican `horizon` meses **de forma recursiva** —idéntico a
    `predict` en producción—, comparando contra los valores reales observados. Así se valida
    el horizonte que de verdad se entrega (no solo 1 paso). La línea base es la **persistencia**
    (último valor observado antes del origen, arrastrado por todo el horizonte).

    `make_estimator` permite inyectar un estimador alternativo (challenger) para comparar bajo el
    MISMO backtest; por defecto usa el HGB de producción con `hgb_params`. Debe ser un callable
    sin argumentos que devuelva un estimador estilo scikit-learn (con `.fit`/`.predict`).

    Devuelve un dict de arrays alineados {step, y_true, y_pred, baseline, vol} (+ n_origins,
    horizon) o None si no hay periodos suficientes.
    """
    # Arrastra `poblacion` (exógena) por el backtest; en modo "rate" se usa para pasar a tasa
    # al entrenar y reconvertir la predicción a conteo al evaluar.
    extra = ["poblacion"] if "poblacion" in series.columns else []
    base = KEY + ["periodo", TARGET] + extra
    s = series[base].sort_values(KEY + ["periodo"]).copy()  # SIEMPRE en conteos
    periodos = np.sort(s["periodo"].unique())
    horizon = int(max(1, min(horizon, len(periodos) - 2)))
    last_origin = len(periodos) - horizon
    if last_origin < 1:
        return None
    first_origin = max(1, last_origin - n_splits + 1)
    max_lag = max(LAGS)
    acc: dict[str, list] = {
        k: [] for k in ("step", "y_true", "y_pred", "baseline", "bl_season", "scale", "vol")
    }
    n_origins = 0
    for oi in range(first_origin, last_origin + 1):
        origin = periodos[oi]
        train_df = s[s["periodo"] < origin]  # conteos + poblacion
        # Entrena en el ESPACIO DE MODELADO (tasa en modo "rate"); features sobre la tasa.
        tf = make_features(_as_modeling_target(train_df, mode)).dropna(subset=[f"lag_{max_lag}"])
        if len(tf) < min_train:
            continue
        est = make_estimator() if make_estimator is not None else _new_estimator(hgb_params)
        est.fit(tf[cols], tf[TARGET])
        n_origins += 1
        # Línea base (persistencia) y volumen para estratificar: en CONTEOS, mode-agnósticos.
        baseline_val = train_df.groupby(KEY)[TARGET].last()
        vol_lookup = train_df.groupby(KEY)[TARGET].mean()
        # Escala de MASE: MAE ingenuo 1-paso DENTRO de la muestra de entrenamiento, por serie
        # (media de |yₜ−yₜ₋₁|). train_df va ordenado por serie+periodo, así que el diff es 1-paso.
        naive_mae = (
            train_df.assign(_d=train_df.groupby(KEY)[TARGET].diff().abs()).groupby(KEY)["_d"].mean()
        )
        hist = _as_modeling_target(train_df, mode).copy()  # recursión en espacio de modelado
        for h, tp in enumerate(periodos[oi : oi + horizon], start=1):
            # Espeja la recursión de producción (`predict`): features de la ÚLTIMA fila observada
            # por serie para pronosticar el mes siguiente, realimentando la predicción (en tasa).
            feats_h = make_features(hist)
            last = feats_h.sort_values(KEY + ["periodo"]).groupby(KEY, dropna=False).tail(1)
            yhat_m = np.clip(est.predict(last[cols]), 0, None)  # tasa (o conteo si mode="count")
            # Reconvierte a CONTEO para evaluar; la población viaja en `last` (constante intra-año).
            if mode == "rate":
                yhat_cnt = yhat_m * _pop_series(last).to_numpy() / RATE_SCALE
            else:
                yhat_cnt = yhat_m
            hist = pd.concat(
                [hist, last[KEY + extra].assign(periodo=tp, **{TARGET: yhat_m})], ignore_index=True
            )
            actual = s[s["periodo"] == tp][KEY + [TARGET]].rename(columns={TARGET: "_y"})
            cmp = last[KEY].assign(_yhat=yhat_cnt).merge(actual, on=KEY, how="inner")
            if cmp.empty:
                continue
            keys_idx = pd.MultiIndex.from_frame(cmp[KEY])
            base_arr = np.nan_to_num(baseline_val.reindex(keys_idx).to_numpy().astype(float))
            vol_arr = vol_lookup.reindex(keys_idx).to_numpy()
            scale_arr = naive_mae.reindex(keys_idx).to_numpy().astype(float)  # MASE (NaN ok)
            # Baseline ESTACIONAL-ingenua: conteo del mismo mes del año anterior (tp−12 meses), por
            # calendario y solo con datos anteriores al origen (tp−12 < origin si h≤12 → sin fuga).
            # Vara más exigente que la persistencia en series con estacionalidad marcada.
            season_tp = pd.Timestamp(tp) - pd.DateOffset(months=12)
            season_lookup = train_df.loc[train_df["periodo"] == season_tp].set_index(KEY)[TARGET]
            season_arr = np.nan_to_num(season_lookup.reindex(keys_idx).to_numpy().astype(float))
            # Predicción ENTREGADA = mezcla modelo+persistencia (la recursión sigue realimentando
            # la del modelo, arriba). La banda/cobertura se calibran sobre este predictor entregado.
            y_served = _BLEND_W * cmp["_yhat"].to_numpy(dtype=float) + (1 - _BLEND_W) * base_arr
            acc["step"].append(np.full(len(cmp), h, dtype=int))
            acc["y_true"].append(cmp["_y"].to_numpy(dtype=float))
            acc["y_pred"].append(y_served)
            acc["baseline"].append(base_arr)
            acc["bl_season"].append(season_arr)
            acc["scale"].append(scale_arr)
            acc["vol"].append(np.nan_to_num(vol_arr.astype(float)))
    if not acc["y_true"]:
        return None
    out = {k: np.concatenate(v) for k, v in acc.items()}
    out["n_origins"] = n_origins
    out["horizon"] = horizon
    return out


def _feature_importance(
    estimator: HistGradientBoostingRegressor,
    X: pd.DataFrame,
    y: pd.Series,
    cols: list[str],
    n_repeats: int = 5,
    sample: int = 20000,
) -> list[dict]:
    """Importancia de features por PERMUTACIÓN (interpretabilidad del modelo global).

    `HistGradientBoostingRegressor` no expone `feature_importances_`; la importancia por
    permutación es agnóstica al modelo y mide la **caída de desempeño (MAE) al barajar cada
    feature**: cuánto depende realmente el pronóstico de cada señal. Se calcula sobre una
    muestra para acotar el costo. Devuelve la lista ordenada de mayor a menor importancia.
    """
    if len(X) > sample:
        idx = np.random.default_rng(settings.seed).choice(len(X), sample, replace=False)
        X, y = X.iloc[idx], y.iloc[idx]
    r = permutation_importance(
        estimator,
        X,
        y,
        n_repeats=n_repeats,
        random_state=settings.seed,
        scoring="neg_mean_absolute_error",
        n_jobs=1,
    )
    ranked = sorted(
        zip(cols, r.importances_mean, r.importances_std, strict=True),
        key=lambda t: t[1],
        reverse=True,
    )
    return [
        {"feature": c, "importancia": round(float(m), 4), "std": round(float(s), 4)}
        for c, m, s in ranked
    ]


def train(
    series: pd.DataFrame, test_months: int = 6, min_nonzero: int = 12, n_splits: int = 3
) -> ForecastModel:
    """Entrena el modelo con backtesting walk-forward recursivo (sin fuga de datos).

    `test_months` es el **horizonte** (en meses) que valida el backtest de forma recursiva
    —el mismo que entrega `predict` en producción— y `n_splits` el número de orígenes
    temporales del rolling. El modelo final se reentrena con TODO el histórico para no
    ignorar los meses más recientes.
    """
    series = _filter_active_series(series, min_nonzero=min_nonzero)
    # Modela TASAS por 100.000 habitantes si hay población (mejora MAE y sMAPE frente a conteos);
    # si la población no está disponible, cae a conteos (comportamiento previo). El backtest,
    # el reporte y `predict` operan en CONTEOS: la tasa es solo el espacio interno de modelado.
    mode = "rate" if _has_population(series) else "count"
    feats = make_features(_as_modeling_target(series, mode)).dropna(subset=[f"lag_{max(LAGS)}"])
    cols = feature_columns(feats)
    if mode == "rate":
        # `tasa_hist` (media_hist/población) es redundante cuando el target YA es una tasa.
        cols = [c for c in cols if c != "tasa_hist"]
    log.info("Target de modelado: %s (%d features)", mode, len(cols))

    if len(feats) < 50:
        raise RuntimeError(
            f"Datos insuficientes para entrenar ({len(feats)} muestras tras filtrar series "
            f"con <{min_nonzero} meses no nulos). Ingestar los datasets completos "
            "(`vigia ingest` sin SODA_MAX_ROWS) o reduzca min_nonzero."
        )

    # Backtest walk-forward RECURSIVO multi-paso contra la línea base ingenua (persistencia).
    # Reporta tanto el error a 1 paso (comparable, headline) como el del horizonte completo
    # que se entrega, su degradación por paso, la cobertura empírica de la banda y el desglose
    # por volumen de serie (que reconcilia el MAE frente a la línea base).
    metrics: dict = {}
    dispersion = 0.0
    pi_scale = _PI_Z
    bt = _walk_forward(series, cols, n_splits=n_splits, horizon=test_months, mode=mode)
    if bt is not None:
        step, yt, yp, bl, vol = bt["step"], bt["y_true"], bt["y_pred"], bt["baseline"], bt["vol"]
        bls, sc = bt["bl_season"], bt["scale"]  # baseline estacional y escala MASE por punto
        one = step == 1
        # Dispersión cuasi-Poisson (Pearson) de los residuos a 1 paso: Var(residuo) ≈ φ·nivel.
        # Da una banda que ESCALA con el nivel de cada serie; un σ global daría intervalos
        # absurdamente estrechos en series de alto volumen (p. ej. Bogotá).
        if one.any():
            r1, p1 = yt[one] - yp[one], yp[one]
            dispersion = float(np.mean(r1**2 / np.maximum(p1, 1.0)))
        # Calibración CONFORMAL de la banda: la forma es heteroscedástica (√φ·√nivel·√paso, igual
        # que en `predict`), pero su ESCALA se ajusta al cuantil empírico de los residuos
        # estandarizados out-of-fold para que la cobertura iguale el nivel nominal (80%), en vez de
        # asumir el cuantil normal (que sobre-cubría al ~94%). Los residuos del walk-forward son OOS
        # (cada origen entrena solo con el pasado), así que esta cobertura es honesta, no in-sample.
        unit = np.sqrt(dispersion * np.maximum(yp, 1.0)) * np.sqrt(step)  # media-anchura unitaria
        std_resid = np.abs(yt - yp) / np.maximum(unit, 1e-9)
        pi_scale = float(np.quantile(std_resid, _PI_LEVEL / 100.0)) if len(std_resid) else _PI_Z
        half = pi_scale * unit
        cobertura = float(np.mean((yt >= yp - half) & (yt <= yp + half))) if len(yt) else 0.0
        m1 = one if one.any() else np.ones(len(yt), dtype=bool)  # a 1 paso (o todo si no hay)
        head = _metrics_block(yt[m1], yp[m1], bl[m1], baseline_season=bls[m1], scale=sc[m1])
        por_volumen = (
            _stratify_by_volume(
                yt[one], yp[one], bl[one], vol[one], baseline_season=bls[one], scale=sc[one]
            )
            if one.any()
            else []
        )
        por_paso = [
            {
                "paso": int(h),
                **_metrics_block(
                    yt[step == h],
                    yp[step == h],
                    bl[step == h],
                    baseline_season=bls[step == h],
                    scale=sc[step == h],
                ),
            }
            for h in range(1, bt["horizon"] + 1)
            if (step == h).any()
        ]

        def _skill(model_mae, base_mae):  # % de mejora relativa (+ = mejor); None si no hay vara
            return (
                round(100.0 * (1.0 - model_mae / base_mae), 1)
                if base_mae not in (None, 0)
                else None
            )

        multipaso = {
            "horizon": int(bt["horizon"]),
            **_metrics_block(yt, yp, bl, baseline_season=bls, scale=sc),
            "pi_cobertura_empirica_pct": round(cobertura * 100, 1),
            "por_paso": por_paso,
        }
        metrics = {
            "backtest": "walk-forward recursivo (rolling origin), sin fuga",
            "n_origins": int(bt["n_origins"]),
            "horizon": int(bt["horizon"]),
            "n_test": head["n"],
            # head lleva mae/smape/baseline_* + baseline_estacional_* + mase/baseline_mase.
            **{k: v for k, v in head.items() if k != "n"},
            "skill_mae_vs_persistencia_pct": _skill(head.get("mae"), head.get("baseline_mae")),
            "skill_mae_vs_estacional_pct": _skill(
                head.get("mae"), head.get("baseline_estacional_mae")
            ),
            "resid_dispersion": round(dispersion, 4),
            "pi_level": _PI_LEVEL,
            "pi_scale": round(pi_scale, 4),
            "pi_cobertura_empirica_pct": round(cobertura * 100, 1),
            "por_volumen": por_volumen,
            "multipaso": multipaso,
        }
        log.info(
            "Backtest walk-forward recursivo (%d orígenes, h=%d): sMAPE 1-paso modelo=%.2f vs "
            "base=%.2f | multipaso modelo=%.2f vs base=%.2f | cobertura PI=%.1f%%",
            bt["n_origins"],
            bt["horizon"],
            head["smape"],
            head["baseline_smape"],
            metrics["multipaso"]["smape"],
            metrics["multipaso"]["baseline_smape"],
            cobertura * 100,
        )

    # Modelo final para PRODUCCIÓN: se reentrena con todo el histórico disponible (incluye
    # los meses más recientes que el backtest reservó para evaluar). A diferencia de un
    # holdout simple, el modelo desplegado no descarta los últimos meses del horizonte.
    model = _new_estimator()
    model.fit(feats[cols], feats[TARGET])

    # Interpretabilidad: importancia por permutación sobre una muestra del conjunto modelado.
    importancias = _feature_importance(model, feats[cols], feats[TARGET], cols)
    if importancias:
        log.info(
            "Top features (permutación): %s",
            ", ".join(f"{d['feature']}={d['importancia']}" for d in importancias[:5]),
        )

    fitted = ForecastModel(
        estimator=model,
        feature_cols=cols,
        last_periodo=series["periodo"].max(),
        metrics=metrics,
        trained_at=datetime.now(UTC).isoformat(),
        resid_dispersion=dispersion,
        pi_scale=pi_scale,
        importancias=importancias,
        target_mode=mode,
    )
    settings.ensure_dirs()
    # El meta se invalida ANTES de reescribir el artefacto y se repone DESPUÉS con escritura a
    # archivo temporal + `replace` (atómico en el mismo directorio): un fallo a mitad de camino
    # deja joblib sin meta (el error de carga degrada al mensaje base), nunca un meta de una
    # ejecución anterior que atribuya el artefacto a una versión equivocada.
    META_PATH.unlink(missing_ok=True)
    joblib.dump(fitted, MODEL_PATH)
    meta_tmp = META_PATH.with_suffix(".tmp")
    meta_tmp.write_text(
        json.dumps(
            {
                "sklearn": sklearn.__version__,
                "numpy": np.__version__,
                "trained_at": fitted.trained_at,
            }
        ),
        encoding="utf-8",
    )
    meta_tmp.replace(META_PATH)
    log.info(
        "Modelo guardado en %s (sklearn %s, numpy %s)",
        MODEL_PATH,
        sklearn.__version__,
        np.__version__,
    )
    return fitted


def load_model() -> ForecastModel:
    """Carga el modelo entrenado desde disco.

    Un `.joblib` pickleado con otra versión de scikit-learn/numpy no se puede deserializar
    (cambian rutas internas, p. ej. `_loss`) y `joblib.load` lanza ModuleNotFoundError. En vez de
    propagar un 500 opaco, se reenvía como RuntimeError accionable: la API lo mapea a 503 y el
    mensaje indica reentrenar para regenerar el artefacto con la versión instalada.
    """
    if not MODEL_PATH.exists():
        raise RuntimeError("Modelo ausente. Ejecute primero `vigia train`.")
    try:
        return joblib.load(MODEL_PATH)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de carga = artefacto inservible
        origen = ""
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
            origen = f"; el artefacto fue entrenado con scikit-learn {meta['sklearn']}"
            if meta.get("numpy"):
                origen += f" y numpy {meta['numpy']}"
            origen += f" el {meta.get('trained_at', '¿fecha desconocida?')}"
        except Exception:  # noqa: BLE001 — sin meta (artefacto anterior al registro de origen) el mensaje base sigue siendo accionable
            pass
        log.error("No se pudo deserializar el modelo (%s): %s", MODEL_PATH, exc)
        raise RuntimeError(
            "Modelo incompatible con las versiones instaladas de scikit-learn "
            f"({sklearn.__version__}) / numpy ({np.__version__}){origen}. Reentrene con "
            "`vigia train` (o `make docker-pipeline`) para regenerarlo."
        ) from exc


def predict(
    series: pd.DataFrame,
    cod_municipio: str,
    categoria: str,
    horizon: int = 6,
    model: ForecastModel | None = None,
) -> list[dict]:
    """Pronóstico recursivo de `horizon` meses para un municipio y categoría."""
    model = model or load_model()
    hist = (
        series[(series["cod_municipio"] == cod_municipio) & (series["categoria"] == categoria)]
        .sort_values("periodo")
        .copy()
    )
    if hist.empty:
        return []

    # En modo "rate" la recursión opera sobre la TASA (espacio de modelado); cada paso se
    # reconvierte a conteo con la población para servir/banda. La población es ~constante intra-año
    # y se arrastra en la última fila.
    mode = getattr(model, "target_mode", "count")
    persist = float(hist[TARGET].iloc[-1])  # persistencia: último CONTEO observado (origen)
    hist = _as_modeling_target(hist, mode)

    # Dispersión del backtest (en CONTEOS); la banda escala con el nivel pronosticado
    # (heteroscedástica) y crece con √paso porque el error se acumula en la recursión. Su escala
    # `pi_scale` se calibró empíricamente (conformal) para que la cobertura iguale el 80% nominal.
    phi = getattr(model, "resid_dispersion", 0.0) or 0.0
    pi_scale = getattr(model, "pi_scale", _PI_Z) or _PI_Z

    results: list[dict] = []
    for step in range(1, horizon + 1):
        feats = make_features(hist)
        x = feats.iloc[[-1]][model.feature_cols]
        yhat_m = float(np.clip(model.estimator.predict(x)[0], 0, None))  # tasa (o conteo)
        if mode == "rate":
            pop = float(_pop_series(feats.iloc[[-1]]).iloc[0])
            yhat_cnt = yhat_m * pop / RATE_SCALE
        else:
            yhat_cnt = yhat_m
        # Predicción entregada: mezcla con persistencia (doma la sobreestimación en alto volumen).
        yhat = _BLEND_W * yhat_cnt + (1 - _BLEND_W) * persist
        half = pi_scale * (phi * max(yhat, 1.0)) ** 0.5 * (step**0.5)
        next_periodo = hist["periodo"].max() + pd.DateOffset(months=1)
        results.append(
            {
                "periodo": next_periodo.strftime("%Y-%m"),
                "prediccion": round(yhat, 2),
                "limite_inferior": round(max(0.0, yhat - half), 2),
                "limite_superior": round(yhat + half, 2),
            }
        )
        # Realimenta la predicción (en el espacio de modelado) para el siguiente paso (recursivo).
        new_row = hist.iloc[[-1]].copy()
        new_row["periodo"] = next_periodo
        new_row[TARGET] = yhat_m
        hist = pd.concat([hist, new_row], ignore_index=True)

    return results
