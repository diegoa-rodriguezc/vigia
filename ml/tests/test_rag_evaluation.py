"""Pruebas del arnés de evaluación del asistente (sin BD ni LLM: answer_fn inyectada).

El arnés debe puntuar igual los DOS caminos de producción (agente con herramientas y RAG
clásico): las respuestas falsas de aquí imitan ambas formas (con y sin campo `modo`).
"""

from dataclasses import dataclass, field

import pandas as pd

from vigia.rag.evaluation import (
    Pregunta,
    _contiene_cifra,
    _contiene_decimal,
    _es_abstencion,
    _extraer_enteros,
    build_golden_set,
    evaluate,
)


@dataclass
class _RespuestaAgente:  # imita rag.agent.AgentAnswer
    answer: str
    sources: list = field(default_factory=list)
    modo: str = "agente"


@dataclass
class _RespuestaClasica:  # imita rag.pipeline.RAGAnswer (sin campo `modo`)
    answer: str
    sources: list = field(default_factory=list)


def test_extraer_enteros_tolerando_separadores():
    txt = "Se registraron 23.029.390 procesos; en 2024 hubo 13,555 casos y 97 en mayo."
    nums = _extraer_enteros(txt)
    assert 23029390 in nums
    assert 13555 in nums
    assert 97 in nums
    assert 2024 in nums


def test_decimal_con_coma_o_punto():
    assert _contiene_decimal("La tasa es 8,51 % a nivel nacional", 8.51)
    assert _contiene_decimal("tasa de 8.51%", 8.51)
    assert not _contiene_decimal("la tasa es 8,5 %", 8.51)


def test_cifra_no_confunde_decimal_con_miles():
    # "8,51" NO debe leerse como 851 (el patrón de miles exige grupos de 3 dígitos).
    assert not _contiene_cifra("la tasa es 8,51 %", [851])


def test_abstencion_detecta_el_rehusar_de_produccion():
    # Prefijo real de pipeline._NO_CONTEXT (normalizado sin acentos en el detector).
    assert _es_abstencion("No encontré información suficiente en los datos abiertos…")
    assert _es_abstencion("Esa pregunta está fuera del alcance de este asistente.")
    # Reencuadre al dominio (la conducta que pide el guardarraíl de alcance estricto del agente).
    assert _es_abstencion(
        "Lo siento, mi función es proporcionar información sobre seguridad y justicia en Colombia."
    )
    assert _es_abstencion("Lamento informarte que no he encontrado información sobre ese tema.")
    # Rehusar pidiendo un municipio válido (sin inventar cifras) también es abstención correcta.
    assert _es_abstencion(
        'Lo siento, no logré identificar el municipio de "San Quimero del Sur". '
        "Por favor proporcione el nombre de un municipio válido."
    )
    assert not _es_abstencion("En Bogotá se registraron 97 homicidios en mayo.")


def test_evaluate_puntua_aciertos_fallos_y_abstenciones():
    preguntas = [
        Pregunta(id="q1", categoria="municipio", texto="¿Total en X?", cifras=[1234567]),
        Pregunta(id="q2", categoria="ranking", texto="¿Dónde más?", texto_esperado="BOGOTÁ"),
        Pregunta(id="q3", categoria="fuera_alcance", texto="¿Capital?", espera_abstencion=True),
        Pregunta(id="q4", categoria="fuera_alcance", texto="¿Dólar?", espera_abstencion=True),
    ]
    canned = {
        "¿Total en X?": _RespuestaAgente("El total es 1.234.567 hechos.", sources=[{"f": 1}]),
        "¿Dónde más?": _RespuestaClasica("El municipio con más casos es Bogota, D.C."),
        "¿Capital?": _RespuestaClasica("No encontré información suficiente en los datos…"),
        # Abstención INCORRECTA: rehúsa pero inventa una cifra "de dato".
        "¿Dólar?": _RespuestaAgente("No puedo, pero el dólar está a 4.100 pesos."),
    }
    rep = evaluate(preguntas, answer_fn=lambda t: canned[t])

    assert rep["n_preguntas"] == 4
    assert rep["exactitud_cifras"] == 1.0  # q1 (cifra) y q2 (texto) aciertan
    assert rep["abstencion_correcta"] == 0.5  # q3 sí; q4 rehúsa pero inventa cifra
    assert rep["citacion_en_aciertos"] == 0.5  # q1 cita, q2 (clásico simulado) no
    modos = {d["id"]: d["modo"] for d in rep["detalle"]}
    assert modos["q1"] == "agente" and modos["q2"] == "rag-clasico"  # ambos caminos puntuados


def test_evaluate_una_pregunta_fallida_no_tumba_el_lote():
    preguntas = [
        Pregunta(id="ok", categoria="municipio", texto="¿A?", cifras=[5]),
        Pregunta(id="boom", categoria="municipio", texto="¿B?", cifras=[7]),
    ]

    def answer_fn(texto):
        if texto == "¿B?":
            raise RuntimeError("proveedor caído")
        return _RespuestaAgente("Son 5 hechos.")

    rep = evaluate(preguntas, answer_fn=answer_fn)
    por_id = {d["id"]: d for d in rep["detalle"]}
    assert por_id["ok"]["acierto"] and not por_id["boom"]["acierto"]
    assert "error" in por_id["boom"]


def test_build_golden_set_derivado_de_gold(tmp_path, monkeypatch):
    """Las preguntas de referencia se DERIVAN de los artefactos vigentes (sin cifras quemadas)."""
    from vigia.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    settings.ensure_dirs()
    pd.DataFrame(
        {
            "cod_municipio": ["11001"],
            "municipio": ["BOGOTÁ, D.C."],
            "departamento": ["BOGOTÁ, D.C."],
            "total_hechos": [1000],
            "total_delitos": [800],
            "primer_anio": [2003],
            "ultimo_anio": [2026],
            "categorias": [20],
        }
    ).to_parquet(settings.gold_dir / "resumen_municipio.parquet", index=False)
    pd.DataFrame(
        {"categoria": ["HOMICIDIO"] * 3, "anio": [2022, 2023, 2024], "cantidad": [10, 11, 12]}
    ).to_parquet(settings.gold_dir / "resumen_categoria.parquet", index=False)

    preguntas = {p.id: p for p in build_golden_set()}

    q = preguntas["muni_11001"]
    assert q.cifras == [1000, 800]  # total_hechos y total_delitos aceptables
    assert "BOGOTÁ" in q.texto and "D.C." not in q.texto  # nombre corto en la pregunta
    # año elegido = max(2024) - 2 = 2022 → cifra de ese año
    assert preguntas["cat_HOMICIDIO_2022"].cifras == [10]
    # las fuera de alcance siempre están (no dependen de artefactos)
    assert any(p.espera_abstencion for p in preguntas.values())
