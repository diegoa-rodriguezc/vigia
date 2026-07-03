"""Pruebas del monitoreo de salud del modelo: PSI, frescura, deriva y backtest extendido."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from vigia.ml.monitoring import backtest_horizon, data_drift, freshness, health_report, psi


def _series(n_series=8, n_meses=60, con_poblacion=True):
    rng = np.random.default_rng(77)
    bloques = []
    for i in range(n_series):
        nivel = 20 + 30 * i
        fechas = pd.period_range("2019-01", periods=n_meses, freq="M").to_timestamp()
        estacional = 5 * np.sin(2 * np.pi * fechas.month / 12)
        cantidad = np.clip(np.round(nivel + estacional + rng.normal(0, 2, n_meses)), 0, None)
        bloque = pd.DataFrame(
            {
                "cod_municipio": [f"{11000 + i:05d}"] * n_meses,
                "municipio": [f"MUNI{i}"] * n_meses,
                "departamento": ["DEP"] * n_meses,
                "categoria": ["HOMICIDIO"] * n_meses,
                "periodo": fechas,
                "cantidad": cantidad.astype(int),
            }
        )
        if con_poblacion:
            bloque["poblacion"] = float(50_000 + 100_000 * i)
        bloques.append(bloque)
    return pd.concat(bloques, ignore_index=True)


def test_psi_cero_para_misma_distribucion():
    rng = np.random.default_rng(1)
    x = rng.poisson(20, 5000)
    assert psi(x, x) == 0.0 or psi(x, x) < 1e-9


def test_psi_detecta_desplazamiento():
    rng = np.random.default_rng(1)
    ref = rng.poisson(20, 5000)
    cur = rng.poisson(60, 5000)  # distribución claramente desplazada
    assert psi(ref, cur) >= 0.25  # deriva significativa


def test_freshness_semaforo():
    s = _series(n_meses=24)  # termina en 2020-12
    # "Hoy" un mes después → rezago pequeño, verde.
    fr = freshness(s, now=datetime(2021, 1, 15, tzinfo=UTC))
    assert fr["lag_meses"] == 1 and fr["estado"] == "verde"
    # "Hoy" un año después → rezago grande, rojo.
    fr2 = freshness(s, now=datetime(2021, 12, 15, tzinfo=UTC))
    assert fr2["lag_meses"] == 12 and fr2["estado"] == "rojo"


def test_data_drift_estructura():
    d = data_drift(_series(), recent_months=6)
    for k in ("psi", "estado", "cambio_volumen_pct", "ventana_meses", "referencia_meses"):
        assert k in d
    assert d["estado"] in ("verde", "amarillo", "rojo")


def test_data_drift_rolling_detecta_shock_reciente():
    """Con referencia rolling, una serie estable da PSI bajo y un shock reciente lo dispara."""
    # Panel amplio (muchas series): el PSI necesita muestra suficiente por ventana para ser estable.
    s = _series(n_series=40, n_meses=48)
    base = data_drift(s, recent_months=6, reference_months=18)
    assert base["estado"] == "verde"  # estable → sin deriva
    assert base["referencia_meses"] == 18
    # Inyecta un shock: triplica los conteos de los últimos 6 meses.
    s2 = s.copy()
    cutoff = (pd.to_datetime(s2["periodo"]).max().to_period("M") - 5).to_timestamp()
    mask = pd.to_datetime(s2["periodo"]) >= cutoff
    s2.loc[mask, "cantidad"] = s2.loc[mask, "cantidad"] * 3
    shocked = data_drift(s2, recent_months=6, reference_months=18)
    assert shocked["psi"] > base["psi"]
    assert shocked["cambio_volumen_pct"] > 100  # ~+200% (triplicado)


def test_backtest_horizon_largo():
    bt = backtest_horizon(_series(), horizon=12, n_splits=2)
    assert bt is not None
    assert bt["horizon"] == 12
    assert bt["por_paso"] and len(bt["por_paso"]) <= 12
    # Pasos consecutivos desde 1.
    assert [p["paso"] for p in bt["por_paso"]] == list(range(1, len(bt["por_paso"]) + 1))
    assert "supera_baseline_mae" in bt


def test_health_report_semaforo_global():
    rep = health_report(_series(), horizon=6, now=datetime(2024, 6, 15, tzinfo=UTC))
    assert rep["estado_global"] in ("verde", "amarillo", "rojo")
    assert {"frescura", "deriva_datos", "backtest_extendido"} <= set(rep)
    # El global es el PEOR de las señales presentes.
    estados = [rep["frescura"]["estado"], rep["deriva_datos"]["estado"]]
    if rep["backtest_extendido"]:
        estados.append(rep["backtest_extendido"]["estado"])
    orden = {"verde": 0, "amarillo": 1, "rojo": 2}
    assert orden[rep["estado_global"]] == max(orden[e] for e in estados)
