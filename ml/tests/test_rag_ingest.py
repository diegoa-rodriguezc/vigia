"""Pruebas del constructor de data cards administrativas (`rag.ingest._admin_cards`).

Verifican, sin BD ni embeddings, que la card de una fuente administrativa lleve un
resumen REAL (rango temporal + desglose por dimensión), no solo el conteo de filas, y
que degrade con elegancia cuando falta la receta o el esquema es inesperado.
"""

import pandas as pd
import pytest

from vigia.rag import ingest


@pytest.fixture
def bronze(tmp_path, monkeypatch):
    """Redirige el directorio bronze a un tmp con parquets sintéticos de las dos fuentes.

    `bronze_dir` es una propiedad calculada (`data_dir / "bronze"`); se redirige el `data_dir`.
    """
    monkeypatch.setattr(ingest.settings, "data_dir", tmp_path)
    bronze_dir = tmp_path / "bronze"
    bronze_dir.mkdir()
    tmp_path = bronze_dir  # los parquets se escriben en el bronze real derivado
    pd.DataFrame(
        {
            "tipo": ["PLAN ANUAL", "PLAN ANUAL", "ORDENADA"],
            "tipo_auditoria": ["INTERNA ESPECÍFICA", "INTERNA ESPECÍFICA", "DE CALIDAD"],
            "unidad": ["PAIS", "DIJIN", "DISAN"],
            "estado_auditoria": ["PROGRAMADA", "PROGRAMADA", "PROGRAMADA"],
            "fecha_inicial": [
                "2017-03-01T00:00:00.000",
                "2020-06-15T00:00:00.000",
                "2026-01-10T00:00:00.000",
            ],
        }
    ).to_parquet(tmp_path / "auditorias.parquet")
    pd.DataFrame(
        {
            "tipo_de_demanda": ["REPARACION DIRECTA", "REPARACION DIRECTA", "OTRAS"],
            "unidad_de_defensa_judical": ["NIVEL CENTRAL", "MEVAL", "NIVEL CENTRAL"],
            "despacho_judicial": ["JUZGADO 1", "JUZGADO 2", "JUZGADO 1"],
            "fecha_de_admisi_n": [
                "1995-10-10T00:00:00.000",
                "2010-01-01T00:00:00.000",
                "2024-05-20T00:00:00.000",
            ],
        }
    ).to_parquet(tmp_path / "demandas_notificadas.parquet")
    return tmp_path


def test_card_administrativa_lleva_resumen_real(bronze):
    cards = ingest._admin_cards()
    assert len(cards) == 2
    por_fuente = {c["metadata"]["fuente"]: c["content"] for c in cards}

    aud = por_fuente["auditorias"]
    assert "3 registros" in aud
    assert "entre 2017 y 2026" in aud  # rango derivado de la columna de fecha
    assert "PLAN ANUAL (2)" in aud  # desglose por dimensión con su conteo
    assert "PROGRAMADA" not in aud  # la columna de valor único no se incluye (no informa)

    dem = por_fuente["demandas_notificadas"]
    assert "entre 1995 y 2024" in dem
    assert "REPARACION DIRECTA (2)" in dem


def test_dimension_de_alta_cardinalidad_muestra_solo_las_de_mayor_volumen(bronze):
    """Con más valores distintos que el tope, la card lista los mayores y declara el total."""
    df = pd.DataFrame(
        {
            "tipo": [f"T{i}" for i in range(10)],
            "fecha_inicial": ["2020-01-01T00:00:00.000"] * 10,
        }
    )
    texto = ingest._admin_card_text(
        "X", df, {"que_es": ".", "fecha": "fecha_inicial", "dims": [("tipo", "origen", 5)]}
    )
    assert "10 distintos, los de mayor volumen" in texto


def test_sin_receta_cae_al_conteo_simple():
    df = pd.DataFrame({"cualquiera": [1, 2, 3]})
    texto = ingest._admin_card_text("Fuente Y", df, None)
    assert "3 registros" in texto
    assert "Fuente Y" in texto
