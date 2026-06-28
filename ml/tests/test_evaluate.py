"""Pruebas del reporte de evaluación: estadísticas y tasa de anomalías."""

import pandas as pd

from vigia.ml.evaluate import _anomaly_stats


def _series_delito(n_series=10, n_meses=24):
    fechas = pd.period_range("2020-01", periods=n_meses, freq="M").to_timestamp()
    bloques = []
    for i in range(n_series):
        bloques.append(
            pd.DataFrame(
                {
                    "cod_municipio": [f"{11000 + i:05d}"] * n_meses,
                    "categoria": ["HOMICIDIO"] * n_meses,
                    "periodo": fechas,
                    "cantidad": [10] * n_meses,
                }
            )
        )
    return pd.concat(bloques, ignore_index=True)


def test_tasa_de_alertas_reframe_el_volumen(tmp_path):
    # 10 series × 24 meses = 240 meses-serie evaluables; 3 anomalías → 1.25%.
    series = _series_delito()
    anomalias = pd.DataFrame(
        {
            "cod_municipio": ["11000", "11000", "11001"],
            "categoria": ["HOMICIDIO"] * 3,
            "severidad": ["ALTA", "MEDIA", "ALTA"],
        }
    )
    path = tmp_path / "anomalias.parquet"
    anomalias.to_parquet(path, index=False)

    stats = _anomaly_stats(series, path=path)
    assert stats["total"] == 3
    assert stats["universo_meses_serie"] == 240
    assert stats["tasa_alertas_pct"] == 1.25
    assert stats["series_evaluadas"] == 10
    assert stats["series_con_alerta"] == 2  # (11000,HOMICIDIO) y (11001,HOMICIDIO)


def test_sin_parquet_devuelve_conteo_cero(tmp_path):
    stats = _anomaly_stats(path=tmp_path / "no_existe.parquet")
    assert stats == {"total": 0, "alta": 0, "media": 0}
