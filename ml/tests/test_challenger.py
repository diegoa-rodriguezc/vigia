"""Prueba del arnés champion/challenger (HGB vs MLP).

Datos sintéticos. Verifica que la comparación corre bajo el mismo backtest y emite métricas
paralelas + veredicto, sin tocar el modelo en producción.
"""

import numpy as np
import pandas as pd

from vigia.ml import challenger


def _series(n_series=6, n_meses=48):
    rng = np.random.default_rng(77)
    bloques = []
    for i in range(n_series):
        nivel = 20 + 30 * i
        fechas = pd.period_range("2019-01", periods=n_meses, freq="M").to_timestamp()
        estacional = 5 * np.sin(2 * np.pi * fechas.month / 12)
        cantidad = np.clip(np.round(nivel + estacional + rng.normal(0, 2, n_meses)), 0, None)
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


def test_compare_produce_metricas_paralelas_y_veredicto():
    cmp = challenger.compare(_series(), test_months=4, n_splits=2)
    for blk in (cmp.champion, cmp.challenger):
        for key in ("mae_1paso", "smape_1paso", "mae_multipaso", "smape_multipaso", "horizon"):
            assert key in blk
        assert blk["mae_multipaso"] >= 0
    assert isinstance(cmp.verdict, str) and cmp.verdict
    # Ambos backtests usan el mismo horizonte y nº de orígenes (comparación pareada).
    assert cmp.champion["horizon"] == cmp.challenger["horizon"]
    assert cmp.champion["n_origins"] == cmp.challenger["n_origins"]
