"""La naturaleza (delito vs respuesta institucional) separa la incidencia delictiva
de la actividad operativa, para que los KPI no las confundan."""

import pandas as pd

from vigia.datasets import RESPONSE_CATEGORIES, naturaleza
from vigia.etl.gold import build_monthly_series


def test_clasificacion_naturaleza():
    assert naturaleza("CAPTURAS") == "respuesta"
    assert naturaleza("INCAUTACION_ARMAS") == "respuesta"
    assert naturaleza("RECUPERACION_VEHICULOS") == "respuesta"
    assert naturaleza("HOMICIDIO") == "delito"
    assert naturaleza("HURTO MOTOCICLETAS") == "delito"
    assert RESPONSE_CATEGORIES == {"CAPTURAS", "INCAUTACION_ARMAS", "RECUPERACION_VEHICULOS"}


def test_serie_mensual_marca_naturaleza():
    eventos = pd.DataFrame(
        {
            "anio": [2020, 2020],
            "mes": [1, 1],
            "cod_departamento": ["11", "11"],
            "departamento": ["BOGOTA", "BOGOTA"],
            "cod_municipio": ["11001", "11001"],
            "municipio": ["BOGOTA", "BOGOTA"],
            "categoria": ["HOMICIDIO", "CAPTURAS"],
            "cantidad": [3, 7],
        }
    )
    serie = build_monthly_series(eventos)
    nat = dict(zip(serie["categoria"], serie["naturaleza"], strict=False))
    assert nat["HOMICIDIO"] == "delito"
    assert nat["CAPTURAS"] == "respuesta"
