"""Pruebas del reporte de evaluación: estadísticas, tasa de anomalías y el RESULTADO CENTRAL
(el modelo supera a la línea base en sMAPE multi-paso — el horizonte que se entrega)."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from vigia.config import settings
from vigia.ml.evaluate import _anomaly_stats, build_model_report


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


def _fake_model(smape_mp: float, baseline_smape_mp: float) -> SimpleNamespace:
    """Modelo mínimo (duck typing) con las métricas que build_model_report necesita para
    computar los flags. Permite fijar el sMAPE multipaso del modelo vs. la línea base."""
    return SimpleNamespace(
        metrics={
            "smape": 120.0,
            "baseline_smape": 118.0,
            "mae": 2.2,
            "baseline_mae": 2.5,
            "multipaso": {"smape": smape_mp, "baseline_smape": baseline_smape_mp},
        },
        trained_at="2026-01-01T00:00:00+00:00",
        feature_cols=["lag_1"],
        importancias=[],
    )


def test_flag_resultado_central_refleja_smape_multipaso():
    """LOGIC GUARD: `supera_linea_base_smape_multipaso` debe ser True SII el sMAPE multipaso del
    modelo < el de la persistencia. Protege contra que el flag se invierta o se desconecte."""
    series = _series_delito()
    gana = build_model_report(series, _fake_model(113.4, 114.7))
    assert gana["supera_linea_base_smape_multipaso"] is True
    pierde = build_model_report(series, _fake_model(120.0, 114.7))
    assert pierde["supera_linea_base_smape_multipaso"] is False


def test_reporte_versionado_muestra_modelo_ganando_multipaso():
    """ARTIFACT GUARD: el reporte versionado (`reports/model_report.json`) debe mostrar el
    resultado central positivo. Si un reentrenamiento revierte la ventaja del modelo sobre la
    persistencia, este test avisa (no pasa en silencio)."""
    path = settings.reports_dir / "model_report.json"
    if not path.exists():
        pytest.skip("model_report.json aún no generado (correr el pipeline)")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["supera_linea_base_smape_multipaso"] is True
    mp = data["metricas_backtest"]["multipaso"]
    assert mp["smape"] < mp["baseline_smape"], "el sMAPE multipaso debe batir a la persistencia"
    # #4: el reporte debe exponer MASE (métrica escalada, no degenerada en conteos dispersos) y la
    # baseline ESTACIONAL (mismo mes del año anterior) junto a la persistencia.
    mb = data["metricas_backtest"]
    assert "mase" in mb and mb["mase"] > 0, "falta MASE en el reporte"
    assert "baseline_estacional_mae" in mb, "falta la baseline estacional en el reporte"
    assert "baseline_estacional_mae" in mp, "falta la baseline estacional multipaso"
    assert isinstance(data["supera_linea_base_estacional_mae_multipaso"], bool)
