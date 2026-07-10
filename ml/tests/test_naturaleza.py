"""La naturaleza (delito vs respuesta institucional) separa la incidencia delictiva
de la actividad operativa, para que los KPI no las confundan."""

import pandas as pd

from vigia.datasets import RESPONSE_CATEGORIES, naturaleza
from vigia.etl.gold import build_gold, build_monthly_series


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


def test_resumen_municipio_cuenta_solo_categorias_de_delito(tmp_path, monkeypatch):
    """`categorias` del resumen municipal excluye las respuestas institucionales: la cifra
    se presenta como "tipos de delito" (tabla, drill-down, cards del RAG) y debe compartir
    universo con el KPI nacional (count DISTINCT ... WHERE naturaleza='delito')."""
    from vigia.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    pd.DataFrame(
        {
            "anio": [2020] * 4,
            "mes": [1] * 4,
            "cod_departamento": ["11"] * 4,
            "departamento": ["BOGOTA"] * 4,
            "cod_municipio": ["11001"] * 4,
            "municipio": ["BOGOTA"] * 4,
            "categoria": ["HOMICIDIO", "HURTO_PERSONAS", "CAPTURAS", "INCAUTACION_ARMAS"],
            "cantidad": [3, 5, 7, 2],
        }
    ).to_parquet(settings.silver_dir / "eventos.parquet", index=False)

    build_gold()

    resumen = pd.read_parquet(settings.gold_dir / "resumen_municipio.parquet")
    fila = resumen.loc[resumen["cod_municipio"] == "11001"].iloc[0]
    assert fila["categorias"] == 2  # HOMICIDIO y HURTO_PERSONAS; no cuenta las 2 respuestas
    assert fila["total_delitos"] == 8
    assert fila["total_respuestas"] == 9
