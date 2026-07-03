"""Integridad del catálogo de fuentes: protege la cifra '20 conjuntos' (16 eventos = 13 delito +
3 respuesta, + 2 administrativos, + DIVIPOLA, + Fiscalía) que declaran el README y CRISP-ML(Q).

Sin este test, añadir/quitar una fuente cambiaría el conteo sin que nada avise, y la documentación
quedaría desalineada del código."""

from vigia.datasets import (
    ADMIN_CATALOG,
    CATALOG,
    DIVIPOLA,
    JUSTICIA_PROCESOS,
    RESPONSE_CATEGORIES,
)


def test_catalogo_16_eventos_13_delito_3_respuesta():
    assert len(CATALOG) == 16
    respuesta = [d for d in CATALOG if d.naturaleza == "respuesta"]
    delito = [d for d in CATALOG if d.naturaleza == "delito"]
    assert len(respuesta) == 3, "capturas + incautación de armas + recuperación de vehículos"
    assert len(delito) == 13


def test_administrativos_y_fuentes_de_referencia():
    assert len(ADMIN_CATALOG) == 2  # auditorías + demandas notificadas
    assert DIVIPOLA.soda_id == "xaxy-8nri"  # nombres/coords oficiales DANE
    assert JUSTICIA_PROCESOS.soda_id == "dbdv-iihs"  # capa paralela Fiscalía


def test_total_20_conjuntos_de_datos_gov_co():
    # 16 eventos + 2 administrativos + DIVIPOLA + Fiscalía = 20 (cifra declarada en la doc).
    total = len(CATALOG) + len(ADMIN_CATALOG) + 1 + 1
    assert total == 20


def test_soda_ids_unicos_sin_duplicar_fuentes():
    ids = (
        [d.soda_id for d in CATALOG]
        + [d.soda_id for d in ADMIN_CATALOG]
        + [DIVIPOLA.soda_id, JUSTICIA_PROCESOS.soda_id]
    )
    assert len(ids) == 20
    assert len(set(ids)) == 20, "no debe haber SODA ids repetidos (doble conteo de una fuente)"


def test_response_categories_se_derivan_del_catalogo():
    # RESPONSE_CATEGORIES se computa desde el catálogo (naturaleza == 'respuesta'), no a mano.
    assert RESPONSE_CATEGORIES == frozenset(
        {"CAPTURAS", "INCAUTACION_ARMAS", "RECUPERACION_VEHICULOS"}
    )
