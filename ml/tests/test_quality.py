"""Pruebas del informe de calidad (QA de la capa silver)."""

import json

import pandas as pd

from vigia.etl.quality import _PLACEHOLDER, quality_report


def _df():
    return pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"]),
            "cod_municipio": ["05001", "05001", "11001", "11001"],
            "categoria": ["HOMICIDIO"] * 4,
            # 2 de 4 valores son marcador → 50% no reportado en este campo
            "sexo": ["MASCULINO", _PLACEHOLDER, _PLACEHOLDER, "FEMENINO"],
            "zona": ["URBANA"] * 4,  # sin placeholders → no debe aparecer en placeholders_pct
            "cantidad": [1, 2, 1, 3],
            "fuente": ["homicidios"] * 4,
        }
    )


def test_placeholders_pct_refleja_no_reportados():
    rep = json.loads(quality_report(_df()))
    # completitud estructural sigue siendo 100% (no hay nulos)
    assert rep["completitud_pct"]["sexo"] == 100.0
    # pero el % real de no reportados se expone aparte
    assert rep["placeholders_pct"]["sexo"] == 50.0
    # los campos sin marcador no se listan (evita ruido)
    assert "zona" not in rep["placeholders_pct"]
    assert "nota_completitud" in rep


def test_municipios_unicos_cuenta_codigos_distintos():
    rep = json.loads(quality_report(_df()))
    assert rep["municipios_unicos"] == 2


def test_alerta_de_truncado_cuando_la_fuente_tiene_tope():
    # build_silver marca `truncado`/`row_cap` en la procedencia de una fuente cortada por
    # SODA_MAX_ROWS; debe elevarse a alerta visible en el informe.
    proc = {
        "homicidios": {
            "filas_crudas": 100,
            "filas_validas": 100,
            "descartadas_pct": 0.0,
            "truncado": True,
            "row_cap": 100,
        }
    }
    rep = json.loads(quality_report(_df(), procedencia=proc))
    assert any("SODA_MAX_ROWS=100" in a for a in rep["alertas"])
    assert any("homicidios" in a for a in rep["alertas"])


def test_sin_alerta_de_truncado_por_defecto():
    # Sin procedencia de truncado, ninguna alerta menciona el tope (ejecución completa).
    rep = json.loads(quality_report(_df()))
    assert not any("SODA_MAX_ROWS" in a for a in rep["alertas"])


def test_placeholders_pct_con_string_dtype():
    """Regresión: silver convierte el texto con `.astype('string')` (StringDtype, no object).

    Con el filtro antiguo `dtype == object`, esas columnas se saltaban y `placeholders_pct`
    salía vacío `{}` pese a haber no-reportados. Reproduce el dtype real del pipeline.
    """
    df = _df()
    # Espeja el tipado de silver: campos de texto como pandas StringDtype, no object.
    for col in ("cod_municipio", "categoria", "sexo", "zona", "fuente"):
        df[col] = df[col].astype("string")

    rep = json.loads(quality_report(df))
    assert rep["placeholders_pct"], "placeholders_pct no debe quedar vacío con StringDtype"
    assert rep["placeholders_pct"]["sexo"] == 50.0
    assert "zona" not in rep["placeholders_pct"]
