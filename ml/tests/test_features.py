"""Pruebas de ingeniería de features: la propiedad crítica es la NO fuga de datos."""

import numpy as np
import pandas as pd

from vigia.ml.features import feature_columns, make_features


def _serie(n_meses=24, base=10):
    fechas = pd.period_range("2020-01", periods=n_meses, freq="M").to_timestamp()
    return pd.DataFrame(
        {
            "cod_municipio": ["11001"] * n_meses,
            "categoria": ["HOMICIDIO"] * n_meses,
            "periodo": fechas,
            "cantidad": np.arange(base, base + n_meses),
        }
    )


def test_lag1_no_usa_el_valor_actual():
    feats = make_features(_serie())
    # lag_1 en t debe ser exactamente la cantidad en t-1 (sin fuga del valor actual).
    assert feats["lag_1"].iloc[5] == feats["cantidad"].iloc[4]
    assert pd.isna(feats["lag_1"].iloc[0])


def test_media_hist_solo_pasado():
    feats = make_features(_serie(base=0))  # cantidades 0,1,2,3,...
    # En la fila índice 4 (cantidad=4), la media histórica = mean(0,1,2,3) = 1.5
    assert feats["media_hist"].iloc[4] == 1.5
    # La primera fila no tiene pasado -> NaN
    assert pd.isna(feats["media_hist"].iloc[0])
    assert feats["meses_activos"].iloc[4] == 4


def test_feature_columns_incluye_identidad():
    cols = feature_columns(make_features(_serie()))
    for c in ("media_hist", "meses_activos", "lag_1", "roll_mean_3", "mes_sin"):
        assert c in cols
