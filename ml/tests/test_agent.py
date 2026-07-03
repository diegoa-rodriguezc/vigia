"""Tests del agente RAG con herramientas (`rag.agent`, `rag.tools`).

Herméticos: no requieren base de datos, datos gold ni red. Se usa un LLM FALSO que emite
turnos guionizados y se parchea `tools.execute`, de modo que se valida la **lógica del bucle**
(selección de herramienta, encadenado, síntesis y fallback) sin invocar modelos reales.
"""

from __future__ import annotations

from vigia.rag import agent, tools
from vigia.rag.providers import ToolCall, Turn

# ───────────────────────── Registro de herramientas ─────────────────────────


def test_execute_unknown_tool_no_lanza():
    out = tools.execute("herramienta_inexistente", {})
    assert "error" in out


def test_execute_argumentos_invalidos_no_lanza():
    # 'resolver_municipio' espera 'texto'; enviar otra clave no debe propagar la excepción.
    out = tools.execute("resolver_municipio", {"clave_mala": "x"})
    assert "error" in out


def test_schemas_cubren_todas_las_herramientas():
    a = tools.anthropic_schemas()
    o = tools.openai_schemas()
    nombres = {t.name for t in tools.TOOLS}
    assert {t["name"] for t in a} == nombres
    assert all("input_schema" in t for t in a)
    assert {t["function"]["name"] for t in o} == nombres
    assert all(t["type"] == "function" for t in o)


# ───────────────────────── LLM falso ─────────────────────────


class FakeLLM:
    """Proveedor de prueba: devuelve turnos guionizados y un texto fijo en la síntesis forzada."""

    supports_tools = True
    tool_format = "openai"

    def __init__(self, turns: list[Turn], final: str = "Síntesis final.") -> None:
        self._turns = list(turns)
        self._final = final
        self.generate_llamado = False

    def turn(self, system: str, transcript: list[dict], tools_native: list[dict]) -> Turn:
        return self._turns.pop(0)

    def generate(self, system: str, prompt: str) -> str:
        self.generate_llamado = True
        return self._final


# ───────────────────────── Bucle del agente ─────────────────────────


def test_agente_encadena_herramientas_y_responde(monkeypatch):
    llamadas = []

    def fake_exec(name, args):
        llamadas.append(name)
        if name == "resolver_municipio":
            return {"encontrado": True, "cod_municipio": "76001", "municipio": "CALI"}
        if name == "pronostico":
            return {
                "encontrado": True,
                "categoria": "HOMICIDIO",
                "proyeccion": [{"periodo": "2026-06"}],
            }
        return {"error": "inesperado"}

    monkeypatch.setattr(agent.tools, "execute", fake_exec)
    turns = [
        Turn(tool_calls=[ToolCall("1", "resolver_municipio", {"texto": "Cali"})]),
        Turn(
            tool_calls=[
                ToolCall("2", "pronostico", {"cod_municipio": "76001", "categoria": "HOMICIDIO"})
            ]
        ),
        Turn(text="En Cali se proyectan homicidios estables."),
    ]
    res = agent.answer("¿pronóstico de homicidios en Cali?", llm=FakeLLM(turns))

    assert res.modo == "agente"
    assert llamadas == ["resolver_municipio", "pronostico"]  # eligió y encadenó
    assert len(res.steps) == 2
    assert res.answer.startswith("En Cali")
    assert len(res.sources) == 2  # cada herramienta aportó una fuente citable


def test_agente_sin_evidencia_no_inventa(monkeypatch):
    # Todas las herramientas responden "sin dato": no deben generarse fuentes y el LLM redacta
    # con esa evidencia vacía (anti-alucinación: no se fabrican cifras).
    monkeypatch.setattr(
        agent.tools, "execute", lambda n, a: {"encontrado": False, "nota": "sin dato"}
    )
    turns = [
        Turn(tool_calls=[ToolCall("1", "resolver_municipio", {"texto": "Atlantis"})]),
        Turn(text="No tengo datos para ese municipio."),
    ]
    res = agent.answer("¿homicidios en Atlantis?", llm=FakeLLM(turns))
    assert res.sources == []
    assert res.modo == "agente"


def test_agente_sintesis_forzada_al_agotar_pasos(monkeypatch):
    monkeypatch.setattr(agent.tools, "execute", lambda n, a: {"encontrado": True, "x": 1})
    siempre_tool = Turn(tool_calls=[ToolCall("x", "anomalias", {"cod_municipio": "76001"})])
    llm = FakeLLM([], final="Resumen con la evidencia disponible.")
    # Cada turno vuelve a pedir herramienta → agota el presupuesto de pasos.
    llm.turn = lambda s, t, tn: siempre_tool  # type: ignore[assignment]

    res = agent.answer("...", llm=llm, max_steps=2)
    assert llm.generate_llamado is True  # hubo síntesis forzada
    assert res.answer == "Resumen con la evidencia disponible."
    assert len(res.steps) == 2


def test_fallback_a_rag_clasico_si_no_hay_tool_use(monkeypatch):
    from vigia.rag import pipeline

    monkeypatch.setattr(
        "vigia.rag.pipeline.answer",
        lambda q, k=None: pipeline.RAGAnswer(answer="respuesta clásica", sources=[]),
    )

    class SinTools:
        supports_tools = False

    res = agent.answer("hola", llm=SinTools())
    assert res.modo == "rag-clasico"
    assert res.answer == "respuesta clásica"
    assert res.steps == []
