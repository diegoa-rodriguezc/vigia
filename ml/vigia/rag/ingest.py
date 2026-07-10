"""Construcción de la base de conocimiento del RAG en pgvector.

Genera *data cards* (resúmenes en lenguaje natural) a partir de la capa gold y
documentos de contexto, los vectoriza y los indexa en la tabla `kb_chunks`.
La tabla se (re)crea con la dimensión del proveedor de embeddings activo.
"""

from __future__ import annotations

import json

import pandas as pd

from vigia.config import settings
from vigia.logging import get_logger
from vigia.rag.providers import get_embedder

# Nota: `pgvector.psycopg` y `vigia.db` (que arrastran libpq) se importan DENTRO de las
# funciones que tocan la BD (`_recreate_table`, `build_index`), no al nivel de módulo, para
# que las data cards y sus tests se importen sin libpq instalado (mismo patrón que
# `rag/pipeline.py`).

log = get_logger(__name__)


def _top_categorias_por_municipio(serie_path, cods: set[str], top_n: int = 5) -> dict[str, str]:
    """Top-`top_n` categorías (por total de hechos) de cada municipio, en UNA sola pasada.

    Sustituye el patrón O(municipios × filas) —un escaneo completo de la serie por cada
    municipio— por un único `groupby` global + recorte, que escala a millones de filas.
    Devuelve {cod_municipio: "CAT1 (n), CAT2 (n), …"} listo para la data card.
    """
    if not serie_path.exists():
        return {}
    serie = pd.read_parquet(serie_path, columns=["cod_municipio", "categoria", "cantidad"])
    serie = serie[serie["cod_municipio"].isin(cods)]
    agg = (
        serie.groupby(["cod_municipio", "categoria"], observed=True)["cantidad"]
        .sum()
        .reset_index()
        .sort_values("cantidad", ascending=False)
    )
    top = agg.groupby("cod_municipio", observed=True).head(top_n)  # top-N por muni (ya desc)
    return {
        cod: ", ".join(
            f"{c} ({int(v)})" for c, v in zip(grp["categoria"], grp["cantidad"], strict=False)
        )
        for cod, grp in top.groupby("cod_municipio", observed=True)
    }


def _municipio_cards(limit_top: int = 300) -> list[dict]:
    """Genera una data card por municipio (los de mayor volumen) desde gold."""
    path = settings.gold_dir / "resumen_municipio.parquet"
    serie_path = settings.gold_dir / "serie_mensual.parquet"
    if not path.exists():
        return []
    resumen = pd.read_parquet(path).head(limit_top)
    top_by_muni = _top_categorias_por_municipio(serie_path, set(resumen["cod_municipio"]))

    cards: list[dict] = []
    for _, r in resumen.iterrows():
        top_cats = top_by_muni.get(r["cod_municipio"], "")
        text = (
            f"Municipio: {r['municipio']} ({r['departamento']}), código DANE {r['cod_municipio']}. "
            f"Total de hechos registrados: {int(r['total_hechos'])} entre "
            f"{int(r['primer_anio'])} y {int(r['ultimo_anio'])}, en {int(r['categorias'])} "
            f"categorías de delito. Delitos más frecuentes: {top_cats}."
        )
        cards.append(
            {
                "content": text,
                "metadata": {
                    "tipo": "municipio",
                    "cod_municipio": r["cod_municipio"],
                    "municipio": r["municipio"],
                },
            }
        )
    return cards


def _categoria_cards() -> list[dict]:
    """Genera data cards de tendencia por categoría de delito."""
    path = settings.gold_dir / "resumen_categoria.parquet"
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    cards: list[dict] = []
    for cat, sub in df.groupby("categoria"):
        sub = sub.sort_values("anio")
        serie_txt = ", ".join(
            f"{int(a)}: {int(v)}" for a, v in zip(sub["anio"], sub["cantidad"], strict=False)
        )
        cards.append(
            {
                "content": (
                    f"Categoría de delito '{cat}'. Hechos por año a nivel nacional: {serie_txt}."
                ),
                "metadata": {"tipo": "categoria", "categoria": cat},
            }
        )
    return cards


def _ranking_cards(top_n: int = 15) -> list[dict]:
    """Genera, por categoría de delito, el ranking de municipios con MÁS hechos.

    Clave para responder preguntas superlativas ("¿dónde hay más homicidios?"): la
    búsqueda semántica por sí sola no ordena por cantidad, así que se precalcula el
    ranking y se indexa como un fragmento recuperable.
    """
    serie_path = settings.gold_dir / "serie_mensual.parquet"
    if not serie_path.exists():
        return []
    serie = pd.read_parquet(
        serie_path, columns=["municipio", "departamento", "categoria", "cantidad"]
    )
    cards: list[dict] = []
    for cat, sub in serie.groupby("categoria"):
        ranking = (
            sub.groupby(["municipio", "departamento"])["cantidad"]
            .sum()
            .sort_values(ascending=False)
            .head(top_n)
        )
        listed = ", ".join(
            f"{i + 1}. {m} ({d}): {int(v)}" for i, ((m, d), v) in enumerate(ranking.items())
        )
        total = int(sub["cantidad"].sum())
        cards.append(
            {
                "content": (
                    f"¿Dónde hay más {cat}? ¿Qué municipios o ciudades tienen más {cat}? "
                    f"Ranking nacional de municipios con MÁS hechos de {cat} (2003-2026), "
                    f"de mayor a menor. Total nacional: {total}. Top {top_n}: {listed}."
                ),
                "metadata": {"tipo": "ranking", "categoria": cat},
            }
        )
    return cards


# Cómo resumir cada fuente ADMINISTRATIVA para el asistente: la columna de fecha (para el
# rango temporal) y las dimensiones a desglosar —columna cruda de la fuente, etiqueta legible
# y cuántos valores mostrar—. Es declarativo, igual que el catálogo: añadir otra fuente
# administrativa con desglose = una entrada más aquí; si una fuente no tiene receta, su card
# cae al conteo simple (degradación). Las columnas de valor único (p. ej. `estado_auditoria`,
# siempre "PROGRAMADA") se omiten porque no informan.
_ADMIN_SUMMARY: dict[str, dict] = {
    "auditorias": {
        "que_es": (
            "Es el plan de auditorías internas y de control de la gestión de la Policía "
            "Nacional (no una serie de delitos), útil para transparencia y rendición de cuentas."
        ),
        "fecha": "fecha_inicial",
        "dims": [
            ("tipo", "origen", 5),
            ("tipo_auditoria", "modalidad", 6),
            ("unidad", "unidad auditada", 5),
        ],
    },
    "demandas_notificadas": {
        "que_es": (
            "Son los litigios en los que la Policía Nacional es demandada ante la "
            "jurisdicción (no una serie de delitos), útiles para transparencia y "
            "rendición de cuentas."
        ),
        "fecha": "fecha_de_admisi_n",
        "dims": [
            ("tipo_de_demanda", "tipo de demanda", 3),
            ("unidad_de_defensa_judical", "unidad de defensa judicial", 5),
            ("despacho_judicial", "despacho judicial", 5),
        ],
    },
}


def _admin_card_text(name: str, df: pd.DataFrame, recipe: dict | None) -> str:
    """Redacta la data card de una fuente administrativa a partir de su receta.

    Sin receta (o con un esquema inesperado) cae al conteo simple, para no romper el índice
    si una fuente cambia de columnas. Con receta, añade el rango temporal y el desglose por
    cada dimensión (todos los valores, o los de mayor volumen si la columna tiene muchos).
    """
    n = len(df)
    if recipe is None:
        return (
            f"Fuente administrativa '{name}' (datos abiertos, datos.gov.co): {n} registros. "
            f"Información de gestión institucional de la Policía Nacional (no una serie de "
            f"delitos), útil para transparencia y rendición de cuentas."
        )

    periodo = ""
    fecha_col = recipe.get("fecha")
    if fecha_col in df.columns:
        anios = pd.to_datetime(df[fecha_col], errors="coerce").dt.year.dropna()
        if not anios.empty:
            periodo = f" entre {int(anios.min())} y {int(anios.max())}"

    frases: list[str] = []
    for col, etiqueta, top_n in recipe.get("dims", []):
        if col not in df.columns:
            continue
        vc = df[col].value_counts()
        listado = ", ".join(f"{k} ({int(v)})" for k, v in vc.head(top_n).items())
        if len(vc) > top_n:
            frases.append(f"Por {etiqueta} ({len(vc)} distintos, los de mayor volumen): {listado}.")
        else:
            frases.append(f"Por {etiqueta}: {listado}.")

    desglose = " ".join(frases)
    return (
        f"Transparencia institucional — '{name}' (datos abiertos, datos.gov.co): "
        f"{n} registros{periodo}. {desglose} {recipe['que_es']}"
    ).strip()


def _admin_cards() -> list[dict]:
    """Data cards de las fuentes ADMINISTRATIVAS (auditorías, demandas) desde bronze.

    No son series delictivas, pero aportan al eje de transparencia institucional: el asistente
    puede informar sobre la gestión de la Policía Nacional (cuántas auditorías, de qué tipo y
    en qué periodo; cuántas demandas y por qué causa) a partir de un resumen REAL de cada
    fuente (rango temporal + desglose por sus dimensiones), no solo su conteo de filas. Se leen
    de bronze (capa cruda) porque no entran a la serie de eventos; si faltan, se omiten.
    """
    from vigia.datasets import ADMIN_CATALOG

    cards: list[dict] = []
    for spec in ADMIN_CATALOG:
        path = settings.bronze_dir / f"{spec.id}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        cards.append(
            {
                "content": _admin_card_text(spec.name, df, _ADMIN_SUMMARY.get(spec.id)),
                "metadata": {"tipo": "administrativo", "fuente": spec.id},
            }
        )
    return cards


def _justicia_cards(top_muni: int = 200) -> list[dict]:
    """Data cards de la capa "Justicia" (Fiscalía): embudo nacional de judicialización + tasa por
    municipio. Permiten que el asistente responda qué fracción de las noticias criminales supera la
    indagación (dato que ninguna serie de delitos aporta). Capa PARALELA a la Policía (un proceso no
    es un hecho registrado). Si no está su gold, se omite (degrada con elegancia)."""
    resumen_path = settings.gold_dir / "justicia_resumen.parquet"
    if not resumen_path.exists():
        return []
    cards: list[dict] = []

    # 1) Card nacional: embudo + tasa + Advertencias de uso (desde el reporte reproducible).
    report_path = settings.reports_dir / "justicia.json"
    if report_path.exists():
        try:
            rep = json.loads(report_path.read_text(encoding="utf-8"))
            emb = rep.get("embudo_etapas", {})
            adv = " ".join(rep.get("advertencias_uso", []))
            tot = int(rep["total_procesos"])
            tasa = rep["tasa_judicializacion_nacional_pct"]
            ind, jud = int(emb.get("indagacion", 0)), int(emb.get("judicializado", 0))
            cards.append(
                {
                    "content": (
                        f"Justicia (Fiscalía General de la Nación): de {tot} procesos penales "
                        f"(2004-2026), la TASA DE JUDICIALIZACIÓN nacional es {tasa}%: solo esa "
                        f"fracción de las noticias criminales supera la indagación y avanza a "
                        f"investigación, juicio o ejecución de penas. Embudo: indagación {ind}, "
                        f"judicializado {jud}. Es una capa paralela a los delitos de la Policía "
                        f"(un proceso no es un hecho registrado). Advertencias de uso: {adv}"
                    ),
                    "metadata": {"tipo": "justicia", "alcance": "nacional"},
                }
            )
        except Exception:  # noqa: BLE001 — un reporte ausente/corrupto no debe romper el índice
            pass

    # 1b) Cards por TÍTULO del Código Penal (tasa de judicialización por delito, nacional).
    # La card del ranking declara el umbral y nombra explícitamente los extremos, para que el
    # asistente responda "¿qué delito se judicializa menos/más?" con la cifra y su salvedad.
    delito_path = settings.gold_dir / "justicia_delito.parquet"
    if delito_path.exists():
        from vigia.etl.justicia import _MIN_PROCESOS_TASA

        delito = pd.read_parquet(delito_path)
        eleg = delito[
            (delito["procesos_etapa_conocida"] >= _MIN_PROCESOS_TASA)
            & (delito["titulo_delito"] != "Sin información")
        ]
        if not eleg.empty:
            menos = eleg.nsmallest(3, "tasa_judicializacion_pct")
            mas = eleg.nlargest(3, "tasa_judicializacion_pct")

            def _linea(r) -> str:
                return (
                    f"{r['titulo_delito']} (tasa {r['tasa_judicializacion_pct']}%, "
                    f"{int(r['total_procesos'])} procesos)"
                )

            # Redacción a propósito SIN el sintagma "tasa de judicialización nacional": estas
            # cards comparten vocabulario con la card nacional y, si lo repiten, la DESPLAZAN del
            # top de la recuperación para la pregunta por la tasa del país (colisión medida con
            # `vigia rag-eval` el 2026-07-09: el asistente citó la tasa de un título como si
            # fuera la nacional). Lo mismo aplica a las cards por título de abajo.
            cards.append(
                {
                    "content": (
                        "Qué TIPO DE DELITO se judicializa menos (por título del Código Penal, "
                        "taxonomía propia de la Fiscalía). El que MENOS se judicializa es "
                        f"{_linea(menos.iloc[0])}; le siguen "
                        f"{'; '.join(_linea(r) for _, r in menos.iloc[1:].iterrows())}. "
                        f"El que MÁS se judicializa es {_linea(mas.iloc[0])}; le siguen "
                        f"{'; '.join(_linea(r) for _, r in mas.iloc[1:].iterrows())}. "
                        f"El ranking compara solo títulos con al menos {_MIN_PROCESOS_TASA} "
                        "procesos de etapa conocida (con pocos procesos una tasa extrema es "
                        "ruido). La taxonomía penal no es 1:1 con las categorías de la Policía."
                    ),
                    "metadata": {"tipo": "justicia", "alcance": "nacional-delito"},
                }
            )
        for _, r in delito.iterrows():
            cards.append(
                {
                    "content": (
                        f"Título penal «{r['titulo_delito']}» (Código Penal, procesos de la "
                        f"Fiscalía): {int(r['total_procesos'])} procesos, "
                        f"{int(r['n_judicializados'])} superaron la indagación "
                        f"({r['tasa_judicializacion_pct']}% de los de etapa conocida)."
                    ),
                    "metadata": {
                        "tipo": "justicia",
                        "alcance": "nacional-delito",
                        "titulo_delito": r["titulo_delito"],
                    },
                }
            )

    resumen = pd.read_parquet(resumen_path)
    # 2) Cards por municipio (los de mayor volumen de procesos).
    top = resumen.sort_values("total_procesos", ascending=False).head(top_muni)
    for _, r in top.iterrows():
        muni = r["municipio"] if pd.notna(r["municipio"]) else r["cod_municipio"]
        depto = r["departamento"] if pd.notna(r["departamento"]) else "—"
        tp, nj = int(r["total_procesos"]), int(r["n_judicializados"])
        cards.append(
            {
                "content": (
                    f"Justicia en {muni} ({depto}), código DANE {r['cod_municipio']}: {tp} "
                    f"procesos de la Fiscalía, {nj} judicializados (superaron la indagación). "
                    f"Tasa de judicialización: {r['tasa_judicializacion_pct']}%."
                ),
                "metadata": {
                    "tipo": "justicia",
                    "cod_municipio": r["cod_municipio"],
                    "municipio": muni,
                },
            }
        )

    # 3) Ranking superlativo por tasa (municipios con volumen suficiente para estabilidad).
    sig = resumen[resumen["procesos_etapa_conocida"] >= 5000].sort_values(
        "tasa_judicializacion_pct", ascending=False
    )
    if not sig.empty:
        fmt = lambda sub: ", ".join(  # noqa: E731
            f"{i + 1}. {r['municipio']} ({r['departamento']}): {r['tasa_judicializacion_pct']}%"
            for i, (_, r) in enumerate(sub.iterrows())
        )
        cards.append(
            {
                "content": (
                    "¿Dónde se judicializa más o menos? Ranking de municipios por TASA DE "
                    "JUDICIALIZACIÓN de la Fiscalía (entre los de al menos 5000 procesos de etapa "
                    f"conocida). Mayor tasa: {fmt(sig.head(15))}. Menor tasa: "
                    f"{fmt(sig.tail(15).iloc[::-1])}."
                ),
                "metadata": {"tipo": "justicia", "alcance": "ranking"},
            }
        )
    return cards


def _context_docs() -> list[dict]:
    """Documentos de contexto fijos (glosario, alcance, fuentes)."""
    return [
        {
            "content": (
                "VigIA es una plataforma de IA para la seguridad ciudadana y la justicia en "
                "Colombia, desarrollada para el Concurso Datos al Ecosistema 2026. Usa datos "
                "abiertos del catálogo de Seguridad y Defensa publicados en datos.gov.co. Ofrece "
                "pronósticos de criminalidad por municipio, detección de anomalías (alertas "
                "tempranas) y este asistente."
            ),
            "metadata": {"tipo": "contexto", "tema": "acerca_de"},
        },
        {
            "content": (
                "Los datos reflejan hechos registrados o denunciados ante Entidades Públicas, no "
                "la criminalidad real (existe subregistro). Las cifras son agregadas por municipio "
                "y no contienen datos personales. Los pronósticos son una ayuda a la decisión, no "
                "un mecanismo de vigilancia sobre personas."
            ),
            "metadata": {"tipo": "contexto", "tema": "limitaciones"},
        },
    ]


def _recreate_table(dim: int) -> None:
    from vigia.db import get_conn

    with get_conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("DROP TABLE IF EXISTS kb_chunks")
        conn.execute(
            f"""
            CREATE TABLE kb_chunks (
                id        BIGSERIAL PRIMARY KEY,
                content   TEXT NOT NULL,
                metadata  JSONB NOT NULL DEFAULT '{{}}',
                embedding vector({dim}) NOT NULL
            )
            """
        )
        # Base de conocimiento pequeña (cientos de fragmentos): se usa búsqueda EXACTA
        # (sin índice ivfflat), que es instantánea y maximiza la precisión del recall.
        # Para una KB grande, crear un índice ivfflat/hnsw y ajustar las sondas.


def build_index() -> int:
    """Genera las data cards, las vectoriza e indexa en pgvector. Devuelve nº de chunks."""
    from pgvector.psycopg import register_vector

    from vigia.db import get_conn
    from vigia.rag.documents import document_cards

    embedder = get_embedder()
    cards = (
        _municipio_cards()
        + _categoria_cards()
        + _ranking_cards()
        + _admin_cards()
        + _justicia_cards()  # capa "Justicia" (Fiscalía): embudo de judicialización
        + _context_docs()
        + document_cards()  # documentos no estructurados (PDF/Word) de settings.rag_docs_dir
    )
    if not cards:
        log.warning("No hay datos gold para indexar. Ejecute el pipeline ETL primero.")
        return 0

    log.info("Vectorizando %d fragmentos…", len(cards))
    vectors = embedder.embed([c["content"] for c in cards])

    _recreate_table(embedder.dim)
    with get_conn() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO kb_chunks (content, metadata, embedding) VALUES (%s, %s, %s)",
                [
                    (c["content"], json.dumps(c["metadata"], ensure_ascii=False), v)
                    for c, v in zip(cards, vectors, strict=False)
                ],
            )
    log.info("Índice RAG construido: %d fragmentos (dim=%d)", len(cards), embedder.dim)
    return len(cards)
