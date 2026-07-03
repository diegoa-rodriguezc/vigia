"""Pruebas del modelo de pronóstico: backtesting, intervalos y casos borde.

Usan datos sintéticos (sin red ni BD). El modelo se serializa a `models/` (gitignored).
"""

import numpy as np
import pandas as pd

from vigia.ml import forecasting


def _series(n_series=8, n_meses=48):
    rng = np.random.default_rng(77)
    bloques = []
    for i in range(n_series):
        nivel = 20 + 30 * i  # series de escalas muy distintas
        fechas = pd.period_range("2019-01", periods=n_meses, freq="M").to_timestamp()
        estacional = 5 * np.sin(2 * np.pi * fechas.month / 12)
        ruido = rng.normal(0, 2, n_meses)
        cantidad = np.clip(np.round(nivel + estacional + ruido), 0, None)
        bloques.append(
            pd.DataFrame(
                {
                    "cod_municipio": [f"{11000 + i:05d}"] * n_meses,
                    "municipio": [f"MUNI{i}"] * n_meses,
                    "departamento": ["DEP"] * n_meses,
                    "cod_departamento": ["11"] * n_meses,
                    "categoria": ["HOMICIDIO"] * n_meses,
                    "periodo": fechas,
                    "cantidad": cantidad.astype(int),
                    "anio": fechas.year,
                    "mes": fechas.month,
                }
            )
        )
    return pd.concat(bloques, ignore_index=True)


def test_backtest_genera_metricas_y_dispersion():
    model = forecasting.train(_series(), test_months=6)
    for key in ("smape", "baseline_smape", "mae", "baseline_mae", "resid_dispersion", "pi_level",
                "pi_scale"):
        assert key in model.metrics
    assert model.resid_dispersion > 0
    # La escala de la banda se calibró empíricamente (conformal), no es el cuantil normal asumido.
    assert model.pi_scale > 0
    # Por construcción (cuantil empírico OOS al nivel nominal), la cobertura queda cerca del 80%.
    assert 70.0 <= model.metrics["pi_cobertura_empirica_pct"] <= 90.0


def test_mase_escala_por_naive_insample():
    """#4: MASE = MAE/escala_naive por punto; <1 cuando el modelo bate al naive in-sample."""
    y_true = np.array([10.0, 12.0, 11.0, 13.0])
    y_pred = np.array([10.0, 12.0, 11.0, 13.0])  # perfecto → MASE 0
    scale = np.array([2.0, 2.0, 2.0, 2.0])
    assert forecasting._mase(y_true, y_pred, scale) == 0.0
    # Error absoluto medio 1.0 con escala 2.0 → MASE 0.5 (<1 = mejor que el naive).
    y_pred2 = y_true + 1.0
    assert forecasting._mase(y_true, y_pred2, scale) == 0.5
    # Escala nula/indefinida se ignora (serie de historia constante); si TODA lo es → None.
    assert forecasting._mase(y_true, y_pred2, np.array([0.0, np.nan, 0.0, 0.0])) is None


def test_backtest_reporta_mase_y_baseline_estacional():
    """#4: el reporte debe traer MASE y la vara ESTACIONAL (mismo mes del año anterior),
    además de la persistencia; y los skill scores relativos a ambas."""
    model = forecasting.train(_series(), test_months=6)
    m = model.metrics
    for key in ("mase", "baseline_mase", "baseline_estacional_mae", "baseline_estacional_smape",
                "skill_mae_vs_persistencia_pct", "skill_mae_vs_estacional_pct"):
        assert key in m, key
    assert m["mase"] > 0
    # La vara estacional también aparece a nivel multipaso y en el desglose por volumen.
    assert "baseline_estacional_mae" in m["multipaso"]
    assert "mase" in m["multipaso"]
    assert "mase" in m["por_volumen"][0]


def test_backtest_valida_horizonte_volumen_y_cobertura():
    """#4 (desglose por volumen) + #5 (multipaso recursivo + cobertura de la banda)."""
    model = forecasting.train(_series(), test_months=4)
    m = model.metrics
    # test_months ahora gobierna el horizonte validado (ya no es un parámetro muerto).
    assert m["horizon"] == 4
    # #4: desglose por tercil de volumen, con veredicto por estrato.
    assert isinstance(m["por_volumen"], list) and m["por_volumen"]
    assert {"estrato", "mae", "baseline_mae", "gana_modelo"} <= set(m["por_volumen"][0])
    # #5: validación multi-paso recursiva del horizonte que se sirve.
    mp = m["multipaso"]
    assert mp["horizon"] == 4
    assert mp["por_paso"] and len(mp["por_paso"]) <= 4
    assert all(p["paso"] == i + 1 for i, p in enumerate(mp["por_paso"]))
    # Cobertura empírica de la banda ~80%, en rango válido [0, 100].
    assert 0.0 <= m["pi_cobertura_empirica_pct"] <= 100.0


def test_predict_devuelve_intervalos_coherentes():
    series = _series()
    model = forecasting.train(series, test_months=6)
    pts = forecasting.predict(series, "11000", "HOMICIDIO", horizon=6, model=model)
    assert len(pts) == 6
    for p in pts:
        assert p["limite_inferior"] <= p["prediccion"] <= p["limite_superior"]
        assert p["limite_inferior"] >= 0  # no se pronostican conteos negativos
    # La banda de incertidumbre crece (o no decrece) con el horizonte (error recursivo).
    anchos = [p["limite_superior"] - p["limite_inferior"] for p in pts]
    assert anchos[-1] >= anchos[0]


def test_importancia_de_features_se_calcula_y_ordena():
    """#6: interpretabilidad — importancia por permutación, ordenada y con todas las features."""
    model = forecasting.train(_series(), test_months=4)
    imp = model.importancias
    assert imp and len(imp) == len(model.feature_cols)
    assert {"feature", "importancia", "std"} <= set(imp[0])
    # Ordenada de mayor a menor importancia.
    valores = [d["importancia"] for d in imp]
    assert valores == sorted(valores, reverse=True)
    # Las features de la lista son exactamente las del modelo (sin inventar ni faltar).
    assert {d["feature"] for d in imp} == set(model.feature_cols)


def test_predict_municipio_sin_historia_devuelve_vacio():
    series = _series()
    model = forecasting.train(series, test_months=6)
    assert forecasting.predict(series, "99999", "HOMICIDIO", horizon=6, model=model) == []
