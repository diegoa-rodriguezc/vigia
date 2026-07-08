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
    # (más corta que HIST_WINDOW → coincide con la media expansiva)
    assert feats["media_hist"].iloc[4] == 1.5
    # La primera fila no tiene pasado -> NaN
    assert pd.isna(feats["media_hist"].iloc[0])
    assert feats["meses_activos"].iloc[4] == 4


def test_media_hist_ventana_olvida_epocas_superadas():
    """`media_hist` es una media MÓVIL de HIST_WINDOW meses, no expansiva: en series con
    caída secular (p. ej. homicidio metropolitano, −90 % en 20 años) la media de toda la
    historia arrastraba el nivel de épocas superadas y sobreestimaba el pronóstico."""
    from vigia.ml.features import HIST_WINDOW

    n = HIST_WINDOW + 25
    serie = _serie(n_meses=n)
    # 24 meses iniciales de nivel alto (100), luego caída a nivel 2 (secular, no un blip).
    serie["cantidad"] = [100] * 24 + [2] * (n - 24)
    feats = make_features(serie)
    ultima = feats["media_hist"].iloc[-1]
    # La última fila solo "ve" los HIST_WINDOW valores previos (todos = 2): la época de 100
    # ya salió de la ventana. La media expansiva habría dado ≈ (24·100 + 60·2)/84 ≈ 30.
    assert ultima == 2.0
    # Y dentro de la ventana sigue sin fuga: excluye el valor del propio mes.
    assert feats["media_hist"].iloc[24] == 100.0  # primer mes tras la caída: solo ve los 100


def test_feature_columns_incluye_identidad():
    cols = feature_columns(make_features(_serie()))
    for c in ("media_hist", "meses_activos", "lag_1", "roll_mean_3", "mes_sin"):
        assert c in cols
