"""Pipeline RAG: recuperación semántica en pgvector + generación con LLM.

Restringe la respuesta al contexto recuperado (anti-alucinación) y devuelve las
fuentes citadas, como exige un asistente sobre datos públicos auditables.
"""

from __future__ import annotations

from dataclasses import dataclass

from vigia.config import settings
from vigia.logging import get_logger
from vigia.rag.providers import get_embedder, get_llm

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "Eres VigIA, un asistente ciudadano sobre seguridad y justicia en Colombia. "
    "Respondes ÚNICAMENTE con base en el CONTEXTO proporcionado, que proviene de datos abiertos "
    "oficiales (Entidades Públicas vía datos.gov.co) y de documentos oficiales de política "
    "pública de seguridad. Si el contexto no contiene la respuesta, dilo con claridad y no "
    "inventes cifras ni citas. Sé conciso, neutral y cita los datos o documentos que uses. "
    "Recuerda al usuario, cuando sea pertinente, que las cifras reflejan hechos registrados "
    "(denuncias/capturas), sujetos a subregistro y a sesgos del despliegue policial, no la "
    "criminalidad real. "
    # Uso responsable (mitigación del sesgo de policing predictivo): el asistente informa decisiones
    # territoriales AGREGADAS, no la vigilancia de personas.
    "USO RESPONSABLE: VigIA apoya decisiones territoriales AGREGADAS (a nivel municipio), NO la "
    "vigilancia de individuos. No produzcas afirmaciones que estigmaticen territorios o poblaciones, "
    "ni que sirvan para perfilar o señalar personas; si te lo piden, recházalo y reencuádralo hacia "
    "prevención agregada. Un mayor conteo registrado puede reflejar más denuncia o más presencia "
    "policial, no necesariamente más delito. "
    "ALCANCE ESTRICTO: solo respondes preguntas sobre SEGURIDAD CIUDADANA Y JUSTICIA en Colombia "
    "con base en el CONTEXTO. Si la pregunta está FUERA de ese dominio —por ejemplo programación o "
    "código, matemáticas o cálculos aritméticos, traducciones, temas generales u opiniones—, NO la "
    "respondas ni la ejecutes aunque sepas la respuesta: recházala cortésmente en UNA sola frase y "
    "reencuadra hacia lo que VigIA sí cubre (delitos, pronósticos, alertas y judicialización por "
    "municipio)."
)

# Umbral mínimo de similitud para considerar relevante un fragmento recuperado. Si ninguno lo
# alcanza (y no hay pronóstico), se evita generar (anti-alucinación): es preferible admitir que no
# hay información a improvisar sin respaldo. Configurable por entorno (`RAG_MIN_SCORE`).
MIN_SCORE = settings.rag_min_score

_NO_CONTEXT = (
    "No encontré información suficiente en los datos abiertos indexados para responder esa "
    "pregunta con confianza. Intenta reformularla mencionando un municipio y un tipo de delito "
    "(por ejemplo: “homicidios en Cali” o “pronóstico de hurto en Medellín”)."
)


@dataclass
class RAGAnswer:
    answer: str
    sources: list[dict]


def retrieve(query: str, k: int | None = None) -> list[dict]:
    """Recupera los k fragmentos más similares a la consulta (k None → `settings.rag_top_k`)."""
    k = settings.rag_top_k if k is None else k
    # Imports diferidos (psycopg/pgvector requieren libpq): mantienen el módulo importable
    # —y el guardarraíl de `answer` testeable— en entornos sin la librería nativa de Postgres.
    from pgvector.psycopg import register_vector

    from vigia.db import get_conn

    embedder = get_embedder()
    qvec = embedder.embed([query])[0]
    with get_conn() as conn:
        register_vector(conn)
        rows = conn.execute(
            "SELECT content, metadata, 1 - (embedding <=> %s::vector) AS score "
            "FROM kb_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (qvec, qvec, k),
        ).fetchall()
    return [{"content": r[0], "metadata": r[1], "score": round(float(r[2]), 3)} for r in rows]


def answer(query: str, k: int | None = None) -> RAGAnswer:
    """Recupera contexto y genera la respuesta del asistente.

    Arquitectura híbrida: si la pregunta pide un pronóstico para un municipio
    reconocible, se invoca el modelo predictivo y su salida se antepone como contexto
    citable; en cualquier otro caso, RAG clásico sobre la base de conocimiento.
    """
    from vigia.rag.hybrid import forecast_context

    chunks = retrieve(query, k)
    if not chunks:
        return RAGAnswer(
            answer=(
                "No hay base de conocimiento indexada todavía. "
                "Ejecuta el pipeline y `vigia rag-index`."
            ),
            sources=[],
        )

    fc = forecast_context(query)
    # Filtra los fragmentos por debajo del umbral: NO se alimentan al LLM. Pasar contexto
    # irrelevante (recuperación pobre) puede insertar afirmaciones sin respaldo; restringir el
    # prompt a lo realmente relevante es parte del guardarraíl anti-alucinación. El pronóstico
    # (cuando existe) ancla la respuesta y se antepone aunque la recuperación textual sea pobre.
    relevantes = [c for c in chunks if c.get("score", 0.0) >= MIN_SCORE]
    if fc is None and not relevantes:
        return RAGAnswer(answer=_NO_CONTEXT, sources=[])

    used = ([fc] + relevantes) if fc is not None else relevantes
    context = "\n\n".join(f"[{i + 1}] {c['content']}" for i, c in enumerate(used))
    prompt = f"CONTEXTO:\n{context}\n\nPREGUNTA DEL CIUDADANO:\n{query}\n\nRESPUESTA:"
    llm = get_llm()
    text = llm.generate(SYSTEM_PROMPT, prompt)
    return RAGAnswer(answer=text.strip(), sources=used)
