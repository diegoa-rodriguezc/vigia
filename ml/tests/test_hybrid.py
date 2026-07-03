"""Pruebas del enrutado híbrido RAG↔pronóstico (casado de entidades, sin BD ni modelo)."""

import pandas as pd
import pytest

from vigia.config import settings
from vigia.rag.hybrid import (
    forecast_context,
    has_forecast_intent,
    match_categoria,
    match_municipio,
)

_RESUMEN = pd.DataFrame(
    [
        {"cod_municipio": "11001", "municipio": "BOGOTÁ, D.C.", "departamento": "BOGOTÁ"},
        {"cod_municipio": "05001", "municipio": "MEDELLÍN", "departamento": "ANTIOQUIA"},
        {"cod_municipio": "76001", "municipio": "SANTIAGO DE CALI", "departamento": "VALLE"},
        {
            "cod_municipio": "54001",
            "municipio": "SAN JOSÉ DE CÚCUTA",
            "departamento": "N. SANTANDER",
        },
    ]
)


def test_detecta_intencion_de_pronostico():
    assert has_forecast_intent("¿Cuál es el pronóstico de homicidios en Cali?")
    assert has_forecast_intent("qué se espera para el próximo año")
    assert not has_forecast_intent("¿cuántos hurtos hubo en 2020?")


def test_casa_municipio_ignorando_acentos():
    m = match_municipio("pronóstico de homicidios en medellin", _RESUMEN)
    assert m is not None and m["cod_municipio"] == "05001"


def test_casa_forma_corta_de_nombre_compuesto():
    # El usuario escribe la forma corta; el nombre oficial es compuesto.
    bog = match_municipio("pronóstico de homicidios en Bogotá", _RESUMEN)
    cali = match_municipio("y qué pasa en Cali el próximo mes", _RESUMEN)
    cuc = match_municipio("homicidios en Cúcuta", _RESUMEN)
    codes = (bog["cod_municipio"], cali["cod_municipio"], cuc["cod_municipio"])
    assert codes == ("11001", "76001", "54001")


def test_sin_municipio_reconocible_devuelve_none():
    assert match_municipio("pronóstico de homicidios en el país", _RESUMEN) is None


def test_fuzzy_match_tolera_typos():
    """Fallback difuso: un nombre mal escrito casa con el municipio correcto."""
    m = match_municipio("pronóstico de homicidios en Medallin", _RESUMEN)  # MEDELLÍN
    assert m is not None and m["cod_municipio"] == "05001"
    m2 = match_municipio("qué se espera en Bogata el próximo mes", _RESUMEN)  # BOGOTÁ
    assert m2 is not None and m2["cod_municipio"] == "11001"


def test_fuzzy_match_no_inventa_con_texto_sin_relacion():
    """Palabras largas sin parecido a ningún municipio → None (no se arriesga)."""
    assert match_municipio("pronóstico de homicidios en Wakanda", _RESUMEN) is None
    assert match_municipio("qué se espera en Springfield", _RESUMEN) is None


def test_fuzzy_no_se_dispara_si_hay_match_exacto():
    """Con coincidencia exacta, se usa esa (no el fallback difuso)."""
    m = match_municipio("homicidios en Medellín", _RESUMEN)
    assert m is not None and m["cod_municipio"] == "05001"


def test_categoria_por_palabra_clave():
    cats = ["HOMICIDIO", "HURTO AUTOMOTORES", "AMENAZAS"]
    assert match_categoria("pronóstico de homicidios", cats) == "HOMICIDIO"
    assert match_categoria("habrá más robos de carros", cats) == "HURTO AUTOMOTORES"
    assert match_categoria("y el clima", cats) is None


def test_forecast_context_sin_intencion_o_sin_municipio_devuelve_none():
    # Deterministas independientemente de si hay artefactos en disco:
    assert forecast_context("¿cuántos homicidios hubo?") is None  # sin intención
    assert forecast_context("pronóstico de homicidios en el país") is None  # sin municipio


def test_categoria_no_reconocida_no_se_inventa():
    # 'asaltos' no está en el diccionario de categorías: el match debe devolver None
    # (antes el híbrido caía a la categoría más frecuente y respondía algo arbitrario).
    cats = ["HOMICIDIO", "HURTO AUTOMOTORES", "AMENAZAS"]
    assert match_categoria("cuántos asaltos habrá en Cali", cats) is None


def test_forecast_context_con_datos_reales_si_estan_presentes():
    # Camino feliz del híbrido: requiere los artefactos del pipeline (gold + modelo).
    gold_ok = (settings.gold_dir / "serie_mensual.parquet").exists()
    model_ok = (settings.models_dir / "forecaster.joblib").exists()
    if not (gold_ok and model_ok):
        pytest.skip("requiere artefactos del pipeline (make pipeline/deploy)")
    card = forecast_context("pronóstico de homicidios en Bogotá")
    assert card is not None
    assert card["metadata"]["tipo"] == "pronostico"
    assert "Pronóstico" in card["content"]


def test_forecast_context_sin_categoria_reconocida_degrada_a_rag():
    # Municipio reconocible + intención de futuro, pero SIN categoría reconocible:
    # el híbrido no debe inventar un pronóstico (devuelve None → RAG clásico).
    gold_ok = (settings.gold_dir / "serie_mensual.parquet").exists()
    model_ok = (settings.models_dir / "forecaster.joblib").exists()
    if not (gold_ok and model_ok):
        pytest.skip("requiere artefactos del pipeline (make pipeline/deploy)")
    assert forecast_context("qué se espera para Bogotá el próximo mes") is None
