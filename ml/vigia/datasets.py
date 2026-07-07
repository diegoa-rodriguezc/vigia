"""Catálogo de conjuntos de datos abiertos de Seguridad y Defensa (datos.gov.co).

Cada entrada describe cómo ingerir y normalizar la fuente. La capa *silver*
usa `schema_family` y `date_format` para unificar todas las fuentes en un
único modelo de eventos delictivos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    """Especificación de una fuente SODA2 y su mapeo al esquema unificado."""

    id: str  # identificador interno (nombre de archivo en bronze)
    soda_id: str  # id del recurso en datos.gov.co (.../resource/<soda_id>.json)
    name: str  # nombre legible
    schema_family: str  # "A" (cod_muni) | "B" (codigo_dane) | "admin" (no delictivo)
    categoria: str  # categoría de delito por defecto si la fuente no la trae
    date_format: str = "iso"  # "iso" | "dmy" (dd/mm/yyyy)
    is_event: bool = True  # False para fuentes administrativas (no series de delito)
    # Naturaleza de la serie:
    #   "delito"    → incidencia que se quiere prevenir; un repunte es MALA señal.
    #   "respuesta" → resultado operativo de la fuerza pública (capturas, incautaciones,
    #                 recuperaciones); un repunte es BUENA señal, no un riesgo ciudadano.
    # Distinguirlas evita que la detección de anomalías marque "alerta de seguridad"
    # cuando lo que sube es la respuesta institucional (ver ml/vigia/ml/anomaly.py).
    naturaleza: str = "delito"
    notes: str = ""


# Fuentes confirmadas vía inspección de la API SODA2 (ver docs/DATA_DICTIONARY.md).
CATALOG: list[DatasetSpec] = [
    DatasetSpec(
        id="homicidios",
        soda_id="m8fd-ahd9",
        name="Homicidios — Policía Nacional",
        schema_family="A",
        categoria="HOMICIDIO",
        date_format="iso",
    ),
    DatasetSpec(
        id="hurto_vehiculos",
        soda_id="csb4-y6v2",
        name="Hurto a vehículos — Policía Nacional",
        schema_family="A",
        categoria="HURTO_VEHICULOS",
        date_format="iso",
    ),
    DatasetSpec(
        id="violencia_intrafamiliar",
        soda_id="vuyt-mqpw",
        name="Violencia intrafamiliar — Policía Nacional",
        schema_family="B",
        categoria="VIOLENCIA_INTRAFAMILIAR",
        date_format="dmy",
    ),
    DatasetSpec(
        id="amenazas",
        soda_id="meew-mguv",
        name="Amenazas — Policía Nacional",
        schema_family="B",
        categoria="AMENAZAS",
        date_format="dmy",
    ),
    # Nota: esquemas verificados contra la API SODA2. reporte_capturas, incautacion_armas
    # y recuperacion_vehiculos son familia B (codigo_dane de 8 díg., fecha dd/mm/yyyy).
    DatasetSpec(
        id="reporte_capturas",
        soda_id="3jdh-nmwu",
        name="Reporte de capturas — Policía Nacional",
        schema_family="B",
        categoria="CAPTURAS",
        date_format="dmy",
        naturaleza="respuesta",
    ),
    DatasetSpec(
        id="incautacion_armas",
        soda_id="2iz5-9bbz",
        name="Incautación de armas de fuego — Policía Nacional",
        schema_family="B",
        categoria="INCAUTACION_ARMAS",
        date_format="dmy",
        naturaleza="respuesta",
        notes="usa 'municipio_hecho' en vez de 'municipio'",
    ),
    DatasetSpec(
        id="recuperacion_vehiculos",
        soda_id="dhy3-732k",
        name="Recuperación de vehículos — Policía Nacional",
        schema_family="B",
        categoria="RECUPERACION_VEHICULOS",
        date_format="dmy",
        naturaleza="respuesta",
    ),
    DatasetSpec(
        id="hurto_modalidades",
        soda_id="d4fr-sbn2",
        name="Hurto por modalidades — Policía Nacional",
        schema_family="B",
        categoria="HURTO_OTRAS_MODALIDADES",
        date_format="dmy",
        notes="categoría en 'tipo_de_hurto'; modalidades no vehiculares (sin solape)",
    ),
    # ------------------------------------------------------------------------------
    # Expansión desde el Asset Inventory de "Seguridad y Defensa" (uzcf-b9dh).
    # Familia A "mensual" de la Policía Nacional: MISMO esquema que homicidios/
    # hurto_vehiculos (cod_muni 5 díg., fecha_hecho ISO, cantidad), cobertura
    # NACIONAL y actualización MENSUAL — verificados contra la API (ver
    # docs/DATA_DICTIONARY.md). Cubren los delitos de mayor preocupación ciudadana.
    DatasetSpec(
        id="hurto_personas",
        soda_id="4rxi-8m8d",
        name="Hurto a personas — Policía Nacional",
        schema_family="A",
        categoria="HURTO_PERSONAS",
        date_format="iso",
        notes="delito urbano más frecuente; no solapa con hurto_vehiculos/modalidades",
    ),
    DatasetSpec(
        id="hurto_residencias",
        soda_id="7mn7-vzqp",
        name="Hurto a residencias — Policía Nacional",
        schema_family="A",
        categoria="HURTO_RESIDENCIAS",
        date_format="iso",
    ),
    DatasetSpec(
        id="delitos_sexuales",
        soda_id="bz43-8ahq",
        name="Delitos sexuales — Policía Nacional",
        schema_family="A",
        categoria="DELITOS_SEXUALES",
        date_format="iso",
        notes="trae 'sexo' y 'zona' → permite análisis desagregado por género",
    ),
    DatasetSpec(
        id="extorsion",
        soda_id="q2ib-t9am",
        name="Extorsión — Policía Nacional",
        schema_family="A",
        categoria="EXTORSION",
        date_format="iso",
    ),
    DatasetSpec(
        id="secuestro",
        soda_id="d7zw-hpf4",
        name="Secuestro — Policía Nacional",
        schema_family="A",
        categoria="SECUESTRO",
        date_format="iso",
        notes="trae 'tipo_delito' (secuestro extorsivo/simple) → categoría por modalidad",
    ),
    DatasetSpec(
        id="delitos_informaticos",
        soda_id="4v6r-wu98",
        name="Delitos informáticos — Policía Nacional",
        schema_family="A",
        categoria="DELITOS_INFORMATICOS",
        date_format="iso",
        notes="'descripcion_conducta' (no mapeada): categoría única por fuente",
    ),
    DatasetSpec(
        id="terrorismo",
        soda_id="yi5j-5fe9",
        name="Terrorismo — Policía Nacional",
        schema_family="A",
        categoria="TERRORISMO",
        date_format="iso",
    ),
    DatasetSpec(
        id="trata_personas",
        soda_id="95c7-mm6s",
        name="Trata de personas — Policía Nacional",
        schema_family="A",
        categoria="TRATA_DE_PERSONAS",
        date_format="iso",
        notes="'descripcion_conducta' (no mapeada): categoría única por fuente",
    ),
    # --- Fuentes evaluadas del Asset Inventory y DESCARTADAS (con justificación) ---
    # mineria_ilicita (4y5w-y5sj): estructura distinta (fecha_de_hecho, sin codigo_dane
    #   ni cantidad) que no encaja en la serie delictiva.
    # Incautación de Estupefacientes (kk69-w2jj) y demás incautaciones de droga: 'cantidad'
    #   en unidades MIXTAS por 'clase_bien' (kg de marihuana vs g de cocaína vs unidades) →
    #   sumarlas no tiene sentido; además son 'respuesta', no delito.
    # Lesiones Personales (72sg-cybi) / Lesiones acc. tránsito (ntej-qq7v): mezclan lesión
    #   intencional (riña) con accidente de tránsito bajo una sola conducta → distorsionarían
    #   la señal de violencia sin una clasificación fila a fila (movilidad, no el reto).
    # HURTO ABIGEATO (p88b-5ac7), PIRATERÍA TERRESTRE (sutf-7dyz), ENTIDADES FINANCIERAS
    #   (i7h7-wmjc): YA contenidos en hurto_modalidades (d4fr-sbn2) → doble conteo.
    # VIOLENCIA INTRAFAMILIAR mensual (gepp-dxcs), Terrorismo trimestral (37p5-impc),
    #   Delitos sexuales trimestral (fpe5-yrmw): duplican (otra periodicidad) fuentes ya
    #   incluidas → se elige una sola versión por delito.
]

# Fuentes administrativas: no entran a la serie de delitos, pero sí al asistente RAG
# como contexto de transparencia institucional (ver rag/ingest._admin_cards).
ADMIN_CATALOG: list[DatasetSpec] = [
    DatasetSpec(
        id="auditorias",
        soda_id="yiu6-gjbe",
        name="Auditorías — Policía Nacional",
        schema_family="admin",
        categoria="AUDITORIAS",
        is_event=False,
    ),
    DatasetSpec(
        id="demandas_notificadas",
        soda_id="4uxk-dt6c",
        name="Demandas notificadas a la Policía Nacional",
        schema_family="admin",
        categoria="DEMANDAS",
        is_event=False,
    ),
]

# Tabla maestra oficial DANE de nombres y coordenadas (no es serie delictiva, pero se
# usa como referencia para asignar el nombre canónico de departamentos/municipios).
DIVIPOLA = DatasetSpec(
    id="divipola",
    soda_id="xaxy-8nri",
    name="DIVIPOLA — Códigos y nombres oficiales DANE (cabeceras y centros poblados)",
    schema_family="reference",
    categoria="REFERENCIA",
    is_event=False,
    notes="fuente oficial de nombres de departamentos/municipios + coordenadas",
)

# Categorías que NO son delito sino resultado operativo de la fuerza pública. Un
# repunte aquí es buena noticia (más capturas/incautaciones/recuperaciones), por lo que
# se excluyen de las "alertas de seguridad" al alza. Derivado del catálogo: si se marca
# otra fuente como `naturaleza="respuesta"`, su categoría entra aquí automáticamente.
RESPONSE_CATEGORIES: frozenset[str] = frozenset(
    d.categoria for d in CATALOG if d.naturaleza == "respuesta"
)


def naturaleza(categoria: str) -> str:
    """Clasifica una categoría como 'delito' o 'respuesta' (resultado operativo).

    Fuente única de verdad para separar la incidencia delictiva (lo que se quiere
    prevenir) de la actividad institucional (capturas, incautaciones, recuperaciones),
    de modo que los KPI y el tablero no las confundan en un mismo total.
    """
    return "respuesta" if categoria in RESPONSE_CATEGORIES else "delito"


# ──────────────────────────────────────────────────────────────────────────────
# Capa "Justicia" — Fiscalía General de la Nación (independiente de la Policía).
# Es MICRO-DATO anonimizado (~23 millones de filas, una por proceso). NO entra a la serie de delitos
# (silver/CATALOG) porque "noticia criminal / proceso" ≠ "hecho registrado" por la Policía →
# sería doble conteo; vive como capa PARALELA. Su valor diferencial es la columna `etapa`
# (Indagación → Investigación → Juicio → Ejecución de Penas), que da el EMBUDO DE
# JUDICIALIZACIÓN — una señal de Justicia que ningún conteo de delitos aporta.
#
# INGESTA POR STREAMING (no server-side): el backend de este dataset es tan lento que la
# agregación `count(1)`+`$group` NO es viable (hasta un `count(*)` tarda ~80 s y cualquier
# `$group` revienta el timeout; un app token no lo arregla — es límite de cómputo, no de cuota).
# Por eso se traen SOLO las columnas de grupo por keyset (:id) y se agrega LOCALMENTE (ver
# `soda.fetch_streamed_aggregate`): páginas estrechas de 50.000 filas en ~2-3 s, ~13 min el total,
# reproducible SIN token. Esquema verificado contra la API.
@dataclass(frozen=True)
class AggregatedSpec:
    """Fuente SODA2 ENORME que se ingiere por streaming de columnas + agregación LOCAL.

    No se descarga el micro-dato completo ni se agrega en el servidor (su backend no lo soporta):
    se paginan solo `group_cols` por keyset y se cuentan en memoria (`count_as`).
    """

    id: str
    soda_id: str
    name: str
    group_cols: tuple[str, ...]  # columnas por las que se agrupa (se traen crudas y se cuentan)
    count_as: str = "n"  # nombre de la columna de conteo resultante
    where: str | None = None  # $where opcional (filtro server-side ligero; el keyset se añade aparte)
    notes: str = ""


JUSTICIA_PROCESOS = AggregatedSpec(
    id="justicia_procesos",
    soda_id="dbdv-iihs",  # "Procesos Fiscalía - V3" (público; la V2 es privada → 403)
    name="Procesos — Fiscalía General de la Nación (V3)",
    # Grano municipio×año×etapa. Al agregar LOCALMENTE, el año SÍ puede ir en el grupo (no hay que
    # particionar para esquivar el timeout, como sí haría falta server-side). 'Sin Información' en
    # año/código se filtra después, en `etl/justicia.py`.
    group_cols=("cod_dane_hecho", "etapa", "a_o_hecho"),
    count_as="n_procesos",
    notes="micro-dato anonimizado (~23 millones de filas) agregado por streaming keyset; "
    "'etapa' = embudo de judicialización",
)


EVENT_DATASETS: dict[str, DatasetSpec] = {d.id: d for d in CATALOG}
REFERENCE_DATASETS: dict[str, DatasetSpec] = {DIVIPOLA.id: DIVIPOLA}
ALL_DATASETS: dict[str, DatasetSpec] = {d.id: d for d in CATALOG + ADMIN_CATALOG + [DIVIPOLA]}
