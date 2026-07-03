"""Pruebas de detección de anomalías: detecta picos relativos a cada serie."""

import numpy as np
import pandas as pd

from vigia.ml.anomaly import detect


def _serie(cod, nivel, n_meses=36, spike_idx=None, spike_val=None, categoria="HOMICIDIO"):
    rng = np.random.default_rng(abs(hash((cod, categoria))) % (2**32))
    fechas = pd.period_range("2020-01", periods=n_meses, freq="M").to_timestamp()
    cantidad = np.clip(np.round(rng.normal(nivel, max(1, nivel * 0.1), n_meses)), 0, None).astype(
        int
    )
    if spike_idx is not None:
        cantidad[spike_idx] = spike_val
    return pd.DataFrame(
        {
            "cod_municipio": [cod] * n_meses,
            "municipio": [f"M{cod}"] * n_meses,
            "departamento": ["DEP"] * n_meses,
            "categoria": [categoria] * n_meses,
            "periodo": fechas,
            "cantidad": cantidad,
        }
    )


def test_detecta_pico_en_serie_de_alto_volumen():
    grande = _serie("11001", nivel=200, spike_idx=30, spike_val=2000)
    pequena = _serie("05002", nivel=4)  # serie estable de bajo volumen, sin pico
    res = detect(pd.concat([grande, pequena], ignore_index=True))
    assert not res.empty
    assert (res["cantidad"] == 2000).any()


def test_pico_relativo_en_serie_pequena_no_queda_eclipsado_por_la_escala():
    # Antes (IsolationForest sin normalizar) los municipios grandes dominaban; ahora la
    # atipicidad es relativa a cada serie, así que un pico proporcional en una serie
    # pequeña también es detectable.
    grande = _serie("11001", nivel=300)  # serie grande estable, SIN pico
    pequena = _serie("05002", nivel=5, spike_idx=25, spike_val=80)
    res = detect(pd.concat([grande, pequena], ignore_index=True))
    assert (res["cod_municipio"] == "05002").any()


def test_pico_en_categoria_de_respuesta_no_genera_alerta():
    # Un repunte de CAPTURAS (resultado operativo, no delito) NO debe marcarse como
    # alerta de seguridad, aunque sea estadísticamente atípico: subir capturas es bueno.
    capturas = _serie("11001", nivel=100, spike_idx=30, spike_val=1500, categoria="CAPTURAS")
    res = detect(capturas)
    assert res.empty

    # Control: el MISMO patrón en una categoría de delito (HOMICIDIO) sí se detecta.
    homicidios = _serie("11001", nivel=100, spike_idx=30, spike_val=1500, categoria="HOMICIDIO")
    assert not detect(homicidios).empty


def _panel_con_inyeccion(n_series=40, n_meses=60, spikes_por_serie=1, seed=77):
    """Panel sintético con picos INYECTADOS en posiciones conocidas (ground truth).

    Permite medir precisión/recall del detector contra anomalías que sabemos verdaderas.
    """
    rng = np.random.default_rng(seed)
    fechas = pd.period_range("2019-01", periods=n_meses, freq="M").to_timestamp()
    meses = fechas.month.to_numpy()
    bloques, verdad = [], set()
    for i in range(n_series):
        base = 20 + 5 * i  # escalas muy distintas entre series
        estacional = 3 * np.sin(2 * np.pi * meses / 12)
        ruido = rng.normal(0, base * 0.08, n_meses)
        y = np.clip(np.round(base + estacional + ruido), 0, None).astype(float)
        cod = f"{11000 + i:05d}"
        for p in rng.choice(range(12, n_meses), spikes_por_serie, replace=False):
            y[int(p)] = base * 4  # pico inequívocamente atípico (4× el nivel)
            verdad.add((cod, fechas[int(p)]))
        bloques.append(
            pd.DataFrame(
                {
                    "cod_municipio": [cod] * n_meses,
                    "municipio": [f"M{i}"] * n_meses,
                    "departamento": ["D"] * n_meses,
                    "categoria": ["HOMICIDIO"] * n_meses,
                    "periodo": fechas,
                    "cantidad": y.astype(int),
                }
            )
        )
    return pd.concat(bloques, ignore_index=True), verdad


def _precision_recall(series, verdad):
    res = detect(series)
    detectadas = {(r.cod_municipio, r.periodo) for r in res.itertuples()}
    tp = len(detectadas & verdad)
    fp = len(detectadas - verdad)
    fn = len(verdad - detectadas)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def test_benchmark_precision_recall_anomalias_raras():
    """Régimen realista (anomalías raras, ~1.7% de meses-serie): recall y precisión altos.

    Valida empíricamente que las alertas no son ruido: el detector recupera casi todos los
    picos inyectados con muy pocos falsos positivos. Sustenta la elección de `contamination`.
    """
    series, verdad = _panel_con_inyeccion(spikes_por_serie=1)
    precision, recall = _precision_recall(series, verdad)
    assert recall >= 0.9
    assert precision >= 0.85


def test_benchmark_precision_se_mantiene_alta_con_mas_anomalias():
    """Con anomalías más densas que `contamination`, el detector sacrifica recall ANTES que
    precisión (comportamiento operativo deseable: pocas alertas, casi todas verdaderas)."""
    series, verdad = _panel_con_inyeccion(spikes_por_serie=2)
    precision, recall = _precision_recall(series, verdad)
    assert precision >= 0.9  # casi sin falsos positivos
    assert recall >= 0.5  # recall cae de forma predecible (acotado por contamination)


def test_serie_estable_no_genera_falsos_positivos():
    # Serie determinista con micro-oscilación acotada (sin picos): el filtro z robusto
    # nunca se dispara, así que el consenso no marca falsos positivos.
    fechas = pd.period_range("2020-01", periods=36, freq="M").to_timestamp()
    estable = pd.DataFrame(
        {
            "cod_municipio": ["11001"] * 36,
            "municipio": ["BOGOTA"] * 36,
            "departamento": ["BOGOTA"] * 36,
            "categoria": ["HOMICIDIO"] * 36,
            "periodo": fechas,
            "cantidad": 50 + np.array([0, 1, -1] * 12),
        }
    )
    res = detect(estable)
    assert res.empty
