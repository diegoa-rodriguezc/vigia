"""Pruebas de la interpretación de coordenadas DIVIPOLA (formato con coma decimal)."""

from vigia.etl.divipola import _parse_coord


def test_parse_coord_una_coma():
    assert _parse_coord("4,649251") == 4.649251
    assert _parse_coord("-74,106992") == -74.106992


def test_parse_coord_comas_multiples():
    # '-75,581,775' -> -75.581775 (primera coma = decimal, resto se descarta)
    assert _parse_coord("-75,581,775") == -75.581775
    assert _parse_coord("6,246,631") == 6.246631


def test_parse_coord_invalido():
    assert _parse_coord(None) is None
    assert _parse_coord("") is None
    assert _parse_coord("nan") is None
