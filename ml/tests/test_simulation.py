"""Pruebas del simulador de escenarios "¿y si…?".

Datos sintéticos (sin red ni BD). Validan el invariante central —un escenario sin palancas
reproduce el pronóstico base— y el sentido/magnitud de cada palanca.
"""

import numpy as np
import pandas as pd

from vigia.ml import forecasting
from vigia.ml.simulation import Scenario, _ramp_weight, simulate


def _series(n_series=8, n_meses=48, con_poblacion=True):
    rng = np.random.default_rng(77)
    bloques = []
    for i in range(n_series):
        nivel = 20 + 30 * i
        fechas = pd.period_range("2019-01", periods=n_meses, freq="M").to_timestamp()
        estacional = 5 * np.sin(2 * np.pi * fechas.month / 12)
        ruido = rng.normal(0, 2, n_meses)
        cantidad = np.clip(np.round(nivel + estacional + ruido), 0, None)
        bloque = pd.DataFrame(
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
        if con_poblacion:
            bloque["poblacion"] = float(50_000 + 100_000 * i)
        bloques.append(bloque)
    return pd.concat(bloques, ignore_index=True)


def test_ramp_weight():
    # Sin rampa: efecto pleno desde el primer paso.
    assert _ramp_weight(1, 0) == 1.0
    # Rampa de 3 meses: 1/3, 2/3, 1, y se satura en 1.
    assert _ramp_weight(1, 3) == 1 / 3
    assert _ramp_weight(2, 3) == 2 / 3
    assert _ramp_weight(3, 3) == 1.0
    assert _ramp_weight(6, 3) == 1.0


def test_escenario_sin_palancas_reproduce_base():
    """Invariante central: sin intervención ni shock, el escenario === pronóstico base."""
    series = _series()
    model = forecasting.train(series, test_months=6)
    base = forecasting.predict(series, "11000", "HOMICIDIO", horizon=6, model=model)
    res = simulate(series, "11000", "HOMICIDIO", Scenario(), horizon=6, model=model)
    assert res is not None
    assert [p["prediccion"] for p in res["proyeccion"]] == [p["prediccion"] for p in base]
    assert res["evitados_total"] == 0.0


def test_intervencion_reduce_la_proyeccion():
    series = _series()
    model = forecasting.train(series, test_months=6)
    res = simulate(
        series, "11003", "HOMICIDIO", Scenario(intervencion_pct=-20), horizon=6, model=model
    )
    assert res is not None
    # Cada mes del escenario queda por debajo del base; hechos evitados positivos.
    for d in res["delta"]:
        assert d["escenario"] <= d["base"]
        assert d["evitados"] >= 0
    assert res["evitados_total"] > 0
    # -20% sin rampa: el escenario es ~0.8× el base en cada punto.
    for b, s in zip(res["base"], res["proyeccion"], strict=True):
        assert s["prediccion"] == round(b["prediccion"] * 0.8, 2)


def test_rampa_difiere_el_efecto():
    """Con rampa, el efecto del primer mes es menor que con efecto inmediato."""
    series = _series()
    model = forecasting.train(series, test_months=6)
    inmediato = simulate(
        series, "11003", "HOMICIDIO", Scenario(intervencion_pct=-30), horizon=6, model=model
    )
    con_rampa = simulate(
        series,
        "11003",
        "HOMICIDIO",
        Scenario(intervencion_pct=-30, ramp_meses=4),
        horizon=6,
        model=model,
    )
    # Primer mes: la rampa evita MENOS que el efecto inmediato (efecto parcial).
    assert con_rampa["delta"][0]["evitados"] < inmediato["delta"][0]["evitados"]
    # Acumulado: con rampa se evitan menos hechos en total dentro del horizonte.
    assert con_rampa["evitados_total"] < inmediato["evitados_total"]


def test_shock_poblacion_mueve_la_proyeccion_en_modo_tasa():
    series = _series(con_poblacion=True)
    model = forecasting.train(series, test_months=6)
    assert model.target_mode == "rate"  # con población, el modelo modela tasas
    base = simulate(series, "11003", "HOMICIDIO", Scenario(), horizon=6, model=model)
    shock = simulate(
        series, "11003", "HOMICIDIO", Scenario(shock_poblacion_pct=25), horizon=6, model=model
    )
    # Más población ⇒ más hechos esperados (la tasa se aplica sobre una base mayor).
    assert shock["proyeccion"][0]["prediccion"] != base["proyeccion"][0]["prediccion"]


def test_shock_poblacion_ignorado_sin_poblacion():
    """En modo conteo (sin población DANE) el shock se ignora sin romper: escenario === base."""
    series = _series(con_poblacion=False)
    model = forecasting.train(series, test_months=6)
    assert model.target_mode == "count"
    base = forecasting.predict(series, "11003", "HOMICIDIO", horizon=6, model=model)
    res = simulate(
        series, "11003", "HOMICIDIO", Scenario(shock_poblacion_pct=25), horizon=6, model=model
    )
    assert [p["prediccion"] for p in res["proyeccion"]] == [p["prediccion"] for p in base]


def test_municipio_sin_historia_devuelve_none():
    series = _series()
    model = forecasting.train(series, test_months=6)
    assert (
        simulate(series, "99999", "HOMICIDIO", Scenario(intervencion_pct=-10), model=model) is None
    )
