"""Pruebas de la capa "Justicia" (procesos de la Fiscalía): clasificación de etapa y gold."""

import json

import pandas as pd

from vigia.etl import justicia as J


def test_clasifica_etapa_judicializacion():
    et = pd.Series(
        ["Indagación", "Investigación", "Juicio", "Ejecución De Penas", "Sin Información"]
    )
    clases = J._clasifica_etapa(et).tolist()
    assert clases == [
        "indagacion",
        "judicializado",
        "judicializado",
        "judicializado",
        "desconocido",
    ]


def _bronze():
    # Grano año×etapa (sin mes). municipio 11001 (Bogotá): 100 indagación + 25 juicio + 25
    # ejecución → 50/150 judicializado. municipio 05001 (Medellín): 80 indagación + 20
    # investigación → 20/100. Filas basura que DEBEN descartarse: año 'Sin Información', código '00000'.
    return pd.DataFrame(
        {
            "cod_dane_hecho": ["11001", "11001", "11001", "05001", "05001", "11001", "00000"],
            "a_o_hecho": ["2024", "2024", "2024", "2024", "2024", "Sin Información", "2024"],
            "etapa": [
                "Indagación",
                "Juicio",
                "Ejecución De Penas",
                "Indagación",
                "Investigación",
                "Juicio",
                "Indagación",
            ],
            "n_procesos": ["100", "25", "25", "80", "20", "999", "999"],
        }
    )


def test_build_justicia_tasa_y_descarte(tmp_path, monkeypatch):
    from vigia.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    settings.ensure_dirs()
    _bronze().to_parquet(settings.bronze_dir / "justicia_procesos.parquet", index=False)
    # Evita la dependencia de DIVIPOLA en el test (red/archivo): nombres oficiales simulados.
    monkeypatch.setattr(
        "vigia.etl.divipola.load_municipios",
        lambda: pd.DataFrame(
            {
                "cod_municipio": ["11001", "05001"],
                "municipio": ["BOGOTÁ, D.C.", "MEDELLÍN"],
                "departamento": ["BOGOTÁ, D.C.", "ANTIOQUIA"],
                "cod_departamento": ["11", "05"],
            }
        ),
    )

    anual = J.build_justicia()

    # La fila con año 'Sin Información' y la de código '00000' se descartaron.
    assert set(anual["cod_municipio"].unique()) == {"11001", "05001"}
    assert int(anual["n_procesos"].sum()) == 250  # 150 + 100 (sin las basura 999+999)

    resumen = pd.read_parquet(settings.gold_dir / "justicia_resumen.parquet").set_index(
        "cod_municipio"
    )
    assert resumen.loc["11001", "tasa_judicializacion_pct"] == 33.33  # (25+25)/150
    assert resumen.loc["05001", "tasa_judicializacion_pct"] == 20.0  # 20/100

    rep = json.loads((settings.reports_dir / "justicia.json").read_text(encoding="utf-8"))
    assert rep["total_procesos"] == 250
    assert rep["tasa_judicializacion_nacional_pct"] == 28.0  # (50+20)/250
    assert rep["cobertura"]["municipios"] == 2
