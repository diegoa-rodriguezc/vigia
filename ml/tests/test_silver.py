"""Pruebas de la unificación de esquemas (capa silver), sin acceso a red."""

import pandas as pd

from vigia.datasets import DatasetSpec
from vigia.etl.silver import normalize

SPEC_A = DatasetSpec(
    id="homicidios",
    soda_id="m8fd-ahd9",
    name="Homicidios",
    schema_family="A",
    categoria="HOMICIDIO",
    date_format="iso",
)
SPEC_B = DatasetSpec(
    id="violencia_intrafamiliar",
    soda_id="vuyt-mqpw",
    name="VIF",
    schema_family="B",
    categoria="VIOLENCIA_INTRAFAMILIAR",
    date_format="dmy",
)
SPEC_MOD = DatasetSpec(
    id="hurto_modalidades",
    soda_id="d4fr-sbn2",
    name="Hurto modalidades",
    schema_family="B",
    categoria="HURTO_OTRAS_MODALIDADES",
    date_format="dmy",
)


def test_normalize_familia_a_fecha_iso():
    raw = pd.DataFrame(
        [
            {
                "fecha_hecho": "2003-01-01T00:00:00.000",
                "cod_depto": "11",
                "departamento": "BOGOTA D.C.",
                "cod_muni": "11001",
                "municipio": "BOGOTA D.C.",
                "zona": "URBANA",
                "sexo": "MASCULINO",
                "arma_medio": "ARMA DE FUEGO",
                "cantidad": "1",
            }
        ]
    )
    out = normalize(raw, SPEC_A)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["cod_municipio"] == "11001"
    assert row["anio"] == 2003 and row["mes"] == 1
    assert row["categoria"] == "HOMICIDIO"
    assert row["cantidad"] == 1


def test_normalize_familia_b_fecha_dmy_y_dane8():
    raw = pd.DataFrame(
        [
            {
                "departamento": "CALDAS",
                "municipio": "Manizales (CT)",
                "codigo_dane": "17001000",
                "armas_medios": "SIN EMPLEO DE ARMAS",
                "fecha_hecho": "10/03/2026",
                "genero": "FEMENINO",
                "grupo_etario": "ADULTOS",
                "cantidad": "2",
            }
        ]
    )
    out = normalize(raw, SPEC_B)
    assert len(out) == 1
    row = out.iloc[0]
    # codigo_dane de 8 dígitos -> 5 dígitos de municipio
    assert row["cod_municipio"] == "17001"
    assert row["cod_departamento"] == "17"
    # sufijo "(CT)" removido y normalizado a mayúsculas
    assert row["municipio"] == "MANIZALES"
    assert row["anio"] == 2026 and row["mes"] == 3
    assert row["sexo"] == "FEMENINO"
    assert row["cantidad"] == 2


SPEC_INCAUTACION = DatasetSpec(
    id="incautacion_armas",
    soda_id="2iz5-9bbz",
    name="Incautación",
    schema_family="B",
    categoria="INCAUTACION_ARMAS",
    date_format="dmy",
)


def test_normalize_municipio_hecho():
    """Fuentes que usan 'municipio_hecho' en vez de 'municipio'."""
    raw = pd.DataFrame(
        [
            {
                "departamento": "CUNDINAMARCA",
                "municipio_hecho": "Soacha",
                "codigo_dane": "25754000",
                "clase_bien": "PISTOLA",
                "fecha_hecho": "01/01/2010",
                "cantidad": "1",
            }
        ]
    )
    out = normalize(raw, SPEC_INCAUTACION)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["municipio"] == "SOACHA"
    assert row["cod_municipio"] == "25754"
    assert row["categoria"] == "INCAUTACION_ARMAS"


def test_normaliza_acentos_unifica_municipios():
    """'BOGOTÁ D.C.' y 'BOGOTA D.C.' deben normalizarse al mismo texto sin acentos."""
    raw = pd.DataFrame(
        [
            {
                "fecha_hecho": "2020-01-01T00:00:00.000",
                "cod_muni": "11001",
                "municipio": "BOGOTÁ D.C.",
                "departamento": "BOGOTÁ",
                "cantidad": "1",
            },
            {
                "fecha_hecho": "2020-02-01T00:00:00.000",
                "cod_muni": "11001",
                "municipio": "BOGOTA D.C.",
                "departamento": "BOGOTA",
                "cantidad": "1",
            },
        ]
    )
    out = normalize(raw, SPEC_A)
    assert set(out["municipio"]) == {"BOGOTA D.C."}  # ambas filas convergen
    assert set(out["departamento"]) == {"BOGOTA"}


def test_descarta_fechas_invalidas():
    raw = pd.DataFrame(
        [
            {"fecha_hecho": "fecha-mala", "cod_muni": "11001", "cantidad": "1"},
            {"fecha_hecho": "2020-05-01T00:00:00.000", "cod_muni": "11001", "cantidad": "1"},
        ]
    )
    out = normalize(raw, SPEC_A)
    assert len(out) == 1  # la fila con fecha inválida se descarta


def test_normalize_hurto_modalidades_familia_b_tipo_de_hurto():
    """hurto_modalidades: familia B, categoría en `tipo_de_hurto`, género→sexo, DANE 8→5."""
    raw = pd.DataFrame(
        [
            {
                "departamento": "GUAJIRA",
                "municipio": "La Jagua del Pilar",
                "codigo_dane": "44420000",
                "armas_medios": "NO REPORTADO",
                "fecha_hecho": "28/04/2024",
                "genero": "MASCULINO",
                "grupo_etario": "ADULTOS",
                "tipo_de_hurto": "HURTO ABIGEATO",
                "cantidad": "1",
            }
        ]
    )
    out = normalize(raw, SPEC_MOD)
    assert len(out) == 1
    r = out.iloc[0]
    # toma `tipo_de_hurto` (no la categoría por defecto), en convención canónica con guion bajo
    assert r["categoria"] == "HURTO_ABIGEATO"
    assert r["cod_municipio"] == "44420"  # codigo_dane 8 díg. -> 5
    assert r["cod_departamento"] == "44"
    assert r["sexo"] == "MASCULINO"  # desde `genero`
    assert (r["fecha"].year, r["fecha"].month) == (2024, 4)  # dd/mm/yyyy


SPEC_VEH = DatasetSpec(
    id="hurto_vehiculos",
    soda_id="csb4-y6v2",
    name="Hurto vehículos",
    schema_family="A",
    categoria="HURTO_VEHICULOS",
    date_format="iso",
)


def test_categoria_convencion_canonica_guion_bajo():
    """La categoría derivada de texto libre se unifica a la convención con guion bajo
    (igual que las categorías por defecto), tras quitar el prefijo 'ARTICULO N.'."""
    raw = pd.DataFrame(
        [
            {
                "fecha_hecho": "2024-06-01T00:00:00.000",
                "cod_muni": "11001",
                "municipio": "BOGOTA D.C.",
                "departamento": "BOGOTA",
                "tipo_delito": "ARTICULO 239. HURTO MOTOCICLETAS",
                "cantidad": "1",
            }
        ]
    )
    out = normalize(raw, SPEC_VEH)
    assert out.iloc[0]["categoria"] == "HURTO_MOTOCICLETAS"  # sin 'ARTICULO 239.' y con '_'
