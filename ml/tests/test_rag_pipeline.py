"""Pruebas del guardarraíl anti-alucinación del pipeline RAG.

Simulan recuperación, pronóstico y LLM: validan la LÓGICA de decisión de `answer`
(cuándo se genera y cuándo se rehúsa) sin BD, embeddings ni modelo de lenguaje.
"""

import pytest

from vigia.rag import pipeline
from vigia.rag.pipeline import MIN_SCORE, answer


class _FakeLLM:
    """LLM falso que cuenta invocaciones: permite afirmar que NO se generó."""

    def __init__(self):
        self.calls = 0

    def generate(self, system, prompt):
        self.calls += 1
        self.last_prompt = prompt
        return "  RESPUESTA_GENERADA  "  # con espacios → verifica el .strip() del pipeline


@pytest.fixture
def fake_llm(monkeypatch):
    llm = _FakeLLM()
    monkeypatch.setattr(pipeline, "get_llm", lambda: llm)
    return llm


def _retrieve(monkeypatch, chunks):
    monkeypatch.setattr(pipeline, "retrieve", lambda query, k=5: chunks)


def _forecast(monkeypatch, value):
    import vigia.rag.hybrid as hybrid

    monkeypatch.setattr(hybrid, "forecast_context", lambda query, *a, **k: value)


def test_rehusa_si_recuperacion_pobre_y_sin_pronostico(monkeypatch, fake_llm):
    """Mejor score < MIN_SCORE y sin pronóstico → rehúsa y NO invoca el LLM."""
    _retrieve(monkeypatch, [{"content": "ruido", "metadata": {}, "score": MIN_SCORE - 0.1}])
    _forecast(monkeypatch, None)
    res = answer("pregunta fuera de contexto")
    assert res.sources == []
    assert "No encontré información suficiente" in res.answer
    assert fake_llm.calls == 0  # clave anti-alucinación: no se arriesga una respuesta sin respaldo


def test_genera_si_recuperacion_buena(monkeypatch, fake_llm):
    chunks = [
        {
            "content": "Homicidios en Cali: 100",
            "metadata": {"tipo": "municipio"},
            "score": MIN_SCORE + 0.2,
        }
    ]
    _retrieve(monkeypatch, chunks)
    _forecast(monkeypatch, None)
    res = answer("homicidios en Cali")
    assert res.answer == "RESPUESTA_GENERADA"  # .strip() aplicado
    assert res.sources == chunks
    assert fake_llm.calls == 1


def test_umbral_es_inclusivo(monkeypatch, fake_llm):
    """best_score == MIN_SCORE no es < MIN_SCORE → genera (el límite no rehúsa)."""
    _retrieve(monkeypatch, [{"content": "c", "metadata": {}, "score": MIN_SCORE}])
    _forecast(monkeypatch, None)
    answer("algo")
    assert fake_llm.calls == 1


def test_pronostico_hace_bypass_del_umbral_y_va_primero(monkeypatch, fake_llm):
    """Aun con recuperación pobre, si hay pronóstico se genera y la card se antepone. El
    fragmento débil se EXCLUYE del contexto (endurecimiento): no se alimenta ruido al LLM."""
    poor = [{"content": "ruido", "metadata": {}, "score": MIN_SCORE - 0.2}]
    fc = {"content": "Pronóstico VigIA...", "metadata": {"tipo": "pronostico"}, "score": 1.0}
    _retrieve(monkeypatch, poor)
    _forecast(monkeypatch, fc)
    res = answer("pronóstico de homicidios en Cali")
    assert fake_llm.calls == 1
    assert res.sources == [fc]  # solo el pronóstico: el fragmento débil quedó filtrado
    assert poor[0] not in res.sources
    # El contexto pasado al LLM tiene la card como [1] y NO incluye el ruido de baja relevancia.
    assert "[1] Pronóstico VigIA" in fake_llm.last_prompt
    assert "ruido" not in fake_llm.last_prompt


def test_filtra_fragmentos_debiles_y_conserva_los_fuertes(monkeypatch, fake_llm):
    """Con fragmentos mezclados, solo los que superan el umbral llegan al LLM y a las fuentes."""
    fuerte = {"content": "Homicidios en Cali: 100", "metadata": {}, "score": MIN_SCORE + 0.3}
    debil = {"content": "texto irrelevante", "metadata": {}, "score": MIN_SCORE - 0.05}
    _retrieve(monkeypatch, [fuerte, debil])
    _forecast(monkeypatch, None)
    res = answer("homicidios en Cali")
    assert fake_llm.calls == 1
    assert res.sources == [fuerte]  # el débil no se cita
    assert "texto irrelevante" not in fake_llm.last_prompt


def test_sin_base_de_conocimiento_no_invoca_llm(monkeypatch, fake_llm):
    _retrieve(monkeypatch, [])
    _forecast(monkeypatch, None)
    res = answer("cualquier cosa")
    assert res.sources == []
    assert "base de conocimiento" in res.answer
    assert fake_llm.calls == 0
