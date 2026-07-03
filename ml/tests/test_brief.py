"""Tests del generador de informes municipales (`rag.brief`).

Herméticos: se parchean `tools._load_gold` (panorama) y `tools.execute` (alertas/pronóstico/
justicia) con datos sintéticos, y se usa un LLM FALSO. Se valida que el informe se **ancla a las
cifras reales** (anti-alucinación: el LLM solo recibe el contexto cerrado) y que degrada sin datos.
"""

from __future__ import annotations

import pandas as pd

from vigia.rag import brief


def _serie() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cod_municipio": "05001",
                "categoria": "HOMICIDIO",
                "naturaleza": "delito",
                "periodo": "2024-01",
                "cantidad": 10,
            },
            {
                "cod_municipio": "05001",
                "categoria": "HOMICIDIO",
                "naturaleza": "delito",
                "periodo": "2024-02",
                "cantidad": 5,
            },
            {
                "cod_municipio": "05001",
                "categoria": "HURTO",
                "naturaleza": "delito",
                "periodo": "2024-01",
                "cantidad": 20,
            },
            {
                "cod_municipio": "05001",
                "categoria": "CAPTURAS",
                "naturaleza": "respuesta",
                "periodo": "2024-01",
                "cantidad": 7,
            },
        ]
    )


def _resumen() -> pd.DataFrame:
    return pd.DataFrame(
        [{"cod_municipio": "05001", "municipio": "MEDELLÍN", "departamento": "ANTIOQUIA"}]
    )


def _fake_exec(name, args):
    if name == "anomalias":
        return {
            "encontrado": True,
            "anomalias": [
                {"categoria": "HOMICIDIO", "periodo": "2024-02", "severidad": "alta", "cantidad": 5}
            ],
        }
    if name == "embudo_justicia":
        return {
            "encontrado": True,
            "tasa_judicializacion_pct": 8.5,
            "n_judicializados": 85,
            "total_procesos": 1000,
        }
    if name == "pronostico":
        return {
            "encontrado": True,
            "categoria": "HURTO",
            "banda_pct": 80,
            "proyeccion": [
                {
                    "periodo": "2024-03",
                    "prediccion": 21,
                    "limite_inferior": 15,
                    "limite_superior": 27,
                }
            ],
        }
    return {"error": "inesperado"}


class FakeLLM:
    supports_tools = False

    def __init__(self, text: str = "Informe ejecutivo de prueba.") -> None:
        self._text = text
        self.last_prompt: str | None = None

    def generate(self, system: str, prompt: str) -> str:
        self.last_prompt = prompt
        return self._text


def _patch(monkeypatch):
    serie, resumen = _serie(), _resumen()
    monkeypatch.setattr(
        brief.tools,
        "_load_gold",
        lambda name: {"serie_mensual": serie, "resumen_municipio": resumen}.get(name),
    )
    monkeypatch.setattr(brief.tools, "execute", _fake_exec)


def test_gather_facts_arma_panorama_ordenado(monkeypatch):
    _patch(monkeypatch)
    facts = brief.gather_facts("05001")
    assert facts is not None
    assert facts["municipio"] == "MEDELLÍN"
    pan = facts["panorama"]
    assert pan["total_delitos"] == 35  # 10 + 5 + 20
    assert pan["total_respuestas"] == 7  # CAPTURAS no cuenta como delito
    assert pan["top_delitos"][0] == {"categoria": "HURTO", "total": 20}  # ordenado desc
    assert facts["alertas"] and facts["pronostico"] and facts["justicia"]


def test_build_context_solo_contiene_cifras_reales(monkeypatch):
    _patch(monkeypatch)
    facts = brief.gather_facts("05001")
    ctx = brief.build_context(facts)
    assert "35" in ctx and "HURTO=20" in ctx  # panorama anclado
    assert "8.5%" in ctx  # tasa de judicialización real
    assert "MEDELLÍN" in ctx


def test_render_pasa_solo_el_contexto_al_llm(monkeypatch):
    _patch(monkeypatch)
    facts = brief.gather_facts("05001")
    llm = FakeLLM()
    res = brief.render(facts, llm=llm)
    assert res.informe == "Informe ejecutivo de prueba."
    assert res.cod_municipio == "05001"
    assert res.datos == facts  # cifras auditables adjuntas
    assert res.generado  # fecha de generación
    # Anti-alucinación: el LLM solo vio el contexto cerrado (las cifras reales).
    assert "35" in llm.last_prompt and "1000" in llm.last_prompt


def test_gather_facts_sin_datos_degrada(monkeypatch):
    # Sin tablas gold → None (el endpoint responde 404 / el CLI avisa).
    monkeypatch.setattr(brief.tools, "_load_gold", lambda name: None)
    assert brief.gather_facts("05001") is None


def test_gather_facts_municipio_inexistente(monkeypatch):
    _patch(monkeypatch)
    assert brief.gather_facts("99999") is None
