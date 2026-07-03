"""Pruebas de la validación de anomalías: recall contra eventos y corroboración interna."""

import pandas as pd
import pytest

from vigia.ml.anomaly_validation import corroboration, validate_against_events


def _anoms(rows):
    return pd.DataFrame(rows, columns=["cod_municipio", "categoria", "periodo"]).assign(
        municipio="M", departamento="D", cantidad=10, score_z=4.0, severidad="ALTA"
    )


def test_validate_recall_con_ventana():
    anoms = _anoms(
        [
            ("11001", "HOMICIDIO", "2024-03-01"),
            ("05001", "HURTO", "2024-06-01"),
        ]
    )
    # Evento 1: mismo municipio, 1 mes después de la anomalía → dentro de ±1 (detectado).
    # Evento 2: municipio sin ninguna anomalía → no detectado.
    events = pd.DataFrame(
        [
            {"cod_municipio": "11001", "periodo": "2024-04", "descripcion": "hito A"},
            {"cod_municipio": "76001", "periodo": "2024-04", "descripcion": "hito B"},
        ]
    )
    r = validate_against_events(anoms, events, window_months=1)
    assert r["n_eventos"] == 2
    assert r["n_detectados"] == 1
    assert r["recall"] == 0.5
    detectado = {d["cod_municipio"]: d["detectado"] for d in r["detalle"]}
    assert detectado == {"11001": True, "76001": False}


def test_validate_fuera_de_ventana_no_cuenta():
    anoms = _anoms([("11001", "HOMICIDIO", "2024-01-01")])
    events = pd.DataFrame([{"cod_municipio": "11001", "periodo": "2024-06"}])  # 5 meses después
    r = validate_against_events(anoms, events, window_months=1)
    assert r["n_detectados"] == 0


def test_validate_por_categoria():
    anoms = _anoms([("11001", "HOMICIDIO", "2024-03-01")])
    # Evento de HURTO en el mismo municipio-mes: con by_categoria=True NO casa (categoría distinta).
    events = pd.DataFrame([{"cod_municipio": "11001", "periodo": "2024-03", "categoria": "HURTO"}])
    assert validate_against_events(anoms, events, by_categoria=True)["n_detectados"] == 0
    # Sin filtrar por categoría, el municipio-mes sí casa.
    assert validate_against_events(anoms, events, by_categoria=False)["n_detectados"] == 1


def test_validate_exige_columnas_minimas():
    anoms = _anoms([("11001", "HOMICIDIO", "2024-03-01")])
    with pytest.raises(ValueError):
        validate_against_events(anoms, pd.DataFrame([{"municipio": "Bogotá"}]))


def test_corroboracion_cruza_categorias():
    # Municipio 11001 en 2024-03 tiene DOS categorías atípicas → ambas corroboradas (1 clúster).
    # Municipio 05001 tiene una sola categoría aislada → no corroborada.
    anoms = _anoms(
        [
            ("11001", "HOMICIDIO", "2024-03-01"),
            ("11001", "HURTO", "2024-03-01"),
            ("05001", "HOMICIDIO", "2024-03-01"),
        ]
    )
    c = corroboration(anoms)
    assert c["n_anomalias"] == 3
    assert c["n_corroboradas"] == 2
    assert c["n_clusters_multidelito"] == 1
    assert c["fraccion_corroborada"] == round(2 / 3, 3)


def test_corroboracion_vacia():
    c = corroboration(pd.DataFrame(columns=["cod_municipio", "categoria", "periodo"]))
    assert c["n_anomalias"] == 0 and c["fraccion_corroborada"] == 0.0
