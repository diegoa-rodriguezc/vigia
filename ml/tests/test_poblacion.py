"""Pruebas de la ingesta de población DANE y su cruce en gold / features."""

import io

import openpyxl
import pandas as pd

from vigia.etl.poblacion import _norm, _read_one


def _make_xlsx(rows: list[tuple]) -> bytes:
    """Construye un .xlsx en memoria a partir de filas (para probar el parser)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_norm_quita_acentos_y_mayusculas():
    assert _norm("AÑO") == "ANO"
    assert _norm(" Población ") == "POBLACION"
    assert _norm("Área Geográfica") == "AREA GEOGRAFICA"


def test_read_one_localiza_encabezado_orden_arbitrario_y_solo_total():
    # Encabezado NO en la primera fila y con DPMP antes que MPIO (como el archivo
    # histórico): el parser debe localizarlo y seleccionar columnas por NOMBRE.
    rows = [
        ("ACTUALIZACIÓN POST COVID-19", None, None, None, None, None, None),
        (None, None, None, None, None, None, None),
        ("DP", "DPNOM", "DPMP", "MPIO", "AÑO", "ÁREA GEOGRÁFICA", "Población"),
        ("05", "Antioquia", "Medellín", "5001", 2020, "Cabecera Municipal", 100),
        ("05", "Antioquia", "Medellín", "5001", 2020, "Total", 150),
        ("05", "Antioquia", "Medellín", "5001", 2021, "Total", 160),
        ("00", "Sin dato", "X", "00000", 2020, "Total", 9),  # marcador -> descartado
    ]
    df = _read_one(_make_xlsx(rows))

    assert list(df.columns) == ["cod_municipio", "anio", "poblacion"]
    # Solo el TOTAL municipal (no cabecera/centros poblados).
    assert set(df["anio"]) == {2020, 2021}
    # Código DANE a 5 dígitos (zfill) y sin marcadores '00...'.
    assert (df["cod_municipio"] == "05001").all()
    assert (df["cod_municipio"].str.slice(0, 2) != "00").all()
    assert int(df.loc[df["anio"] == 2020, "poblacion"].iloc[0]) == 150


def test_attach_poblacion_clip_de_anio(monkeypatch):
    """Años fuera del rango DANE se respaldan con el extremo disponible (clip)."""
    import vigia.etl.poblacion as pmod
    from vigia.etl import gold

    pob = pd.DataFrame(
        {"cod_municipio": ["05001", "05001"], "anio": [2005, 2006], "poblacion": [100, 110]}
    )
    monkeypatch.setattr(pmod, "load_poblacion", lambda: pob)

    series = pd.DataFrame({"cod_municipio": ["05001"] * 3, "anio": [2003, 2005, 2030]})
    out = gold._attach_poblacion(series)
    # 2003 -> clip a 2005 (100); 2005 -> 100; 2030 -> clip a 2006 (110)
    assert out["poblacion"].tolist() == [100, 100, 110]


def test_attach_poblacion_degrada_si_falta(monkeypatch):
    """Sin población descargada, la columna queda nula (degradación elegante)."""
    import vigia.etl.poblacion as pmod
    from vigia.etl import gold

    def _raise():
        raise RuntimeError("ausente")

    monkeypatch.setattr(pmod, "load_poblacion", _raise)
    series = pd.DataFrame({"cod_municipio": ["05001"], "anio": [2020]})
    out = gold._attach_poblacion(series)
    assert "poblacion" in out.columns and out["poblacion"].isna().all()


def test_features_exogenas_de_poblacion():
    """`log_poblacion` y `tasa_hist` aparecen como features cuando hay población."""
    from vigia.ml.features import feature_columns, make_features

    periodos = pd.period_range("2020-01", "2021-06", freq="M").to_timestamp()
    df = pd.DataFrame(
        {
            "cod_municipio": "05001",
            "categoria": "HOMICIDIO",
            "periodo": periodos,
            "cantidad": range(len(periodos)),
            "poblacion": 100000,
        }
    )
    f = make_features(df)
    cols = feature_columns(f)
    assert "log_poblacion" in cols and "tasa_hist" in cols
    assert f["log_poblacion"].notna().all()
