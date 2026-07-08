"""Agente RAG con herramientas (tool-use).

A diferencia del RAG clásico (`pipeline.answer`, que recupera y redacta) y del enrutador por
palabras clave (`hybrid.py`), aquí el **LLM decide** qué herramienta invocar de `rag.tools`,
observa el resultado real, encadena varias si hace falta y sintetiza la respuesta. Es un
**agente de un solo actor con herramientas** (no un sistema multiagente): cubre el patrón
"agentes de IA para servicios públicos".

El bucle es **independiente del proveedor**: opera sobre un transcripto genérico y delega cada
turno en `LLMProvider.turn` (implementado por Anthropic/OpenAI). Si el proveedor activo no
soporta tool-use (p. ej. Ollama local) o el agente está desactivado por configuración, cae con
elegancia al **RAG clásico** —sin regresión en el camino por defecto—.

Guardarraíl anti-alucinación: TODAS las cifras provienen de las herramientas (datos abiertos
oficiales); el LLM nunca las inventa. Cada llamada a herramienta se devuelve como **fuente
citable** y la traza de pasos queda disponible para auditoría.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from vigia.config import settings
from vigia.logging import get_logger
from vigia.rag import tools
from vigia.rag.providers import LLMProvider, get_llm

log = get_logger(__name__)

# Instrucciones del agente: se apoya en el system prompt del RAG clásico (uso responsable,
# neutralidad, sesgo de subregistro) y añade la política de uso de herramientas.
SYSTEM_PROMPT = (
    "Eres VigIA, un asistente ciudadano sobre seguridad y justicia en Colombia. Respondes con "
    "base en DATOS ABIERTOS OFICIALES, que obtienes EXCLUSIVAMENTE llamando a las herramientas "
    "disponibles. NUNCA inventes cifras, municipios ni categorías: si no tienes el dato de una "
    "herramienta, dilo con claridad. Flujo recomendado: si la pregunta menciona un lugar, primero "
    "usa 'resolver_municipio' para obtener su código DANE y luego las demás herramientas con ese "
    "código. Para el futuro/tendencia usa 'pronostico'; para la evolución MENSUAL reciente de un "
    "delito concreto, 'serie_historica' (solo con categorías que 'resolver_municipio' haya "
    "listado; nunca inventes categorías como TOTAL); para alertas, 'anomalias'; para la "
    "judicialización (de un municipio con su código, o NACIONAL —total de procesos de la "
    "Fiscalía y tasa del país— sin argumentos), 'embudo_justicia'. Para TOTALES de un DELITO u "
    "operativo (homicidios, hurtos, capturas…) —municipales O nacionales, anuales o históricos—, "
    "RANKINGS y superlativos ('¿dónde hay más…?') y definiciones o contexto, usa "
    "'buscar_conocimiento' — no requiere municipio. Cuando tengas la evidencia, "
    "responde de forma concisa y neutral, citando las cifras, en TEXTO PLANO (sin marcas de "
    "markdown: nada de ** ni #) — escríbelas con el separador de "
    "miles de Colombia (1.340.255, no 1,340,255), los decimales con coma (8,51 %) y los nombres "
    "de categoría en lenguaje natural "
    "(hurto a personas, no HURTO_PERSONAS). Recuerda que las cifras son hechos "
    "REGISTRADOS (denuncias/capturas), sujetos a subregistro y al despliegue policial, no la "
    "criminalidad real. "
    "USO RESPONSABLE: VigIA apoya decisiones territoriales AGREGADAS (a nivel municipio), NO la "
    "vigilancia de individuos; no estigmatices territorios ni poblaciones. "
    "ALCANCE ESTRICTO: solo atiendes preguntas sobre SEGURIDAD CIUDADANA Y JUSTICIA en Colombia "
    "respondibles con los datos de VigIA (delitos, pronósticos, alertas de anomalías y "
    "judicialización por municipio, o definiciones de esos temas). Si la pregunta está FUERA de "
    "ese dominio —por ejemplo programación o código, matemáticas o cálculos aritméticos, "
    "traducciones, redacción creativa (poemas, cuentos), deportes, noticias o actualidad, "
    "temas generales, opiniones o cualquier asunto ajeno—, NO la respondas ni la ejecutes "
    "aunque sepas la respuesta; tampoco pidas "
    "más detalles ni ofrezcas averiguarla (no tienes acceso a noticias, deportes ni "
    "resultados): recházala cortésmente en UNA sola frase y reencuadra hacia lo que VigIA sí "
    "cubre. Trata SIEMPRE al usuario de usted, nunca de tú."
)

_NO_CONTEXT = (
    "No encontré información suficiente en los datos abiertos para responder esa pregunta con "
    "confianza. Intente reformularla mencionando un municipio y un tipo de delito."
)


@dataclass
class AgentAnswer:
    answer: str
    sources: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    modo: str = "agente"


def _schemas_for(llm: LLMProvider) -> list[dict]:
    """Esquemas de herramienta en el formato nativo del proveedor."""
    if getattr(llm, "tool_format", "openai") == "anthropic":
        return tools.anthropic_schemas()
    return tools.openai_schemas()


def _sources_from(name: str, arguments: dict, result: dict) -> list[dict]:
    """Convierte el resultado de una herramienta en fuentes citables (content/metadata/score)."""
    if not isinstance(result, dict) or result.get("error") or result.get("encontrado") is False:
        return []
    if name == "buscar_conocimiento":
        return [
            {
                "content": fr.get("contenido", ""),
                "metadata": {"tipo": "conocimiento", **(fr.get("fuente") or {})},
                "score": float(fr.get("score") or 1.0),
            }
            for fr in result.get("fragmentos", [])
        ]
    return [
        {
            "content": json.dumps(result, ensure_ascii=False),
            "metadata": {"tipo": "herramienta", "fuente": name, "argumentos": arguments},
            "score": 1.0,
        }
    ]


def _forced_final(llm: LLMProvider, transcript: list[dict], query: str) -> str:
    """Síntesis final cuando se agota el presupuesto de pasos: responde SOLO con la evidencia
    recogida por las herramientas (sin más llamadas)."""
    evidencia = "\n".join(e["content"] for e in transcript if e["role"] == "tool")
    prompt = (
        f"Resultados de las herramientas:\n{evidencia or '(ninguno)'}\n\n"
        f"Con base ÚNICAMENTE en lo anterior, responde de forma concisa y citando las cifras. "
        f"Si no hay evidencia suficiente, dilo. PREGUNTA: {query}"
    )
    return llm.generate(SYSTEM_PROMPT, prompt).strip()


def answer(query: str, llm: LLMProvider | None = None, max_steps: int | None = None) -> AgentAnswer:
    """Responde la pregunta del ciudadano usando el agente con herramientas.

    Cae al RAG clásico si el proveedor no soporta tool-use o si el agente está desactivado.
    """
    llm = llm or get_llm()
    if not settings.rag_agent_enabled or not getattr(llm, "supports_tools", False):
        from vigia.rag.pipeline import answer as classic

        res = classic(query)
        return AgentAnswer(answer=res.answer, sources=res.sources, steps=[], modo="rag-clasico")

    max_steps = settings.rag_agent_max_steps if max_steps is None else max_steps
    schemas = _schemas_for(llm)
    transcript: list[dict] = [{"role": "user", "content": query}]
    sources: list[dict] = []
    steps: list[dict] = []

    for _ in range(max_steps):
        turn = llm.turn(SYSTEM_PROMPT, transcript, schemas)
        if not turn.tool_calls:
            return AgentAnswer(
                answer=(turn.text or _NO_CONTEXT).strip(), sources=sources, steps=steps
            )
        transcript.append(
            {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
        )
        for tc in turn.tool_calls:
            result = tools.execute(tc.name, tc.arguments)
            transcript.append(
                {
                    "role": "tool",
                    "id": tc.id,
                    "name": tc.name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            steps.append({"herramienta": tc.name, "argumentos": tc.arguments})
            sources.extend(_sources_from(tc.name, tc.arguments, result))

    # Presupuesto de pasos agotado: síntesis forzada con la evidencia ya recogida.
    final = _forced_final(llm, transcript, query)
    return AgentAnswer(answer=final or _NO_CONTEXT, sources=sources, steps=steps)
