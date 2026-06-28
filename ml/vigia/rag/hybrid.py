"""Conexión híbrida RAG ↔ modelos predictivos.

El asistente, además de recuperar *data cards* estáticas, puede invocar el modelo
de pronóstico cuando el ciudadano pregunta por el futuro de un delito en un
municipio concreto. Así la respuesta combina recuperación (cifras históricas) con
inferencia del modelo (proyección + incertidumbre): una arquitectura híbrida, no
un RAG aislado. Toda la ruta está protegida: ante cualquier fallo (gold/modelo
ausentes, sin coincidencia) devuelve None y el pipeline cae al RAG clásico.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd

from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)

# Calibración del fallback difuso de municipios (typos). Conservador a propósito para no casar
# nombres equivocados: solo tokens largos (los cortos —CALI, CHÍA— dan falsos positivos fáciles),
# similitud alta, y se descarta si dos municipios distintos quedan casi empatados (ambigüedad).
_FUZZY_MIN_LEN = 5
_FUZZY_CUTOFF = 0.82
_FUZZY_MARGIN = 0.03

# Intención de pronóstico: la pregunta mira al futuro.
_FORECAST_HINTS = (
    "pronostic",
    "predic",
    "proyec",
    "futuro",
    "proxim",
    "próxim",
    "tendenc",
    "espera",
)

# Palabras clave → fragmento de categoría (se casa por substring contra las categorías reales).
_CATEGORY_HINTS = {
    "homicid": "HOMICIDIO",
    "hurto": "HURTO",
    "amenaz": "AMENAZAS",
    "intrafamiliar": "VIOLENCIA_INTRAFAMILIAR",
    "violencia": "VIOLENCIA_INTRAFAMILIAR",
    "captur": "CAPTURAS",
    "arma": "INCAUTACION_ARMAS",
    "recuper": "RECUPERACION_VEHICULOS",
    "moto": "HURTO MOTOCICLETAS",
    "vehic": "HURTO AUTOMOTORES",
    "carro": "HURTO AUTOMOTORES",
}


def _norm(s: str) -> str:
    """Mayúsculas sin acentos para casar nombres con escritura inconsistente."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return s.upper().strip()


def has_forecast_intent(query: str) -> bool:
    q = _norm(query).lower()
    return any(h in q for h in _FORECAST_HINTS)


def match_municipio(query: str, resumen: pd.DataFrame) -> dict | None:
    """Casa el municipio mencionado en la consulta por *token* del nombre oficial.

    El nombre oficial DANE suele ser compuesto ('BOGOTÁ, D.C.', 'SANTIAGO DE CALI',
    'SAN JOSÉ DE CÚCUTA') mientras el ciudadano escribe la forma corta ('Bogotá',
    'Cali', 'Cúcuta'). Por eso se casa por token significativo (≥4 letras) presente
    como palabra completa en la consulta, prefiriendo el token más específico (el más
    largo). Si dos municipios distintos empatan en el token más largo, se considera
    ambiguo y no se arriesga una coincidencia (devuelve None).
    """
    qwords = set(re.findall(r"[A-Z0-9]+", _norm(query)))
    candidates: list[tuple[int, str, dict]] = []
    for _, r in resumen.iterrows():
        tokens = [t for t in re.findall(r"[A-Z0-9]+", _norm(r["municipio"])) if len(t) >= 4]
        matched = [t for t in tokens if t in qwords]
        if not matched:
            continue
        best_tok = max(matched, key=len)
        info = {
            "cod_municipio": r["cod_municipio"],
            "municipio": r["municipio"],
            "departamento": r["departamento"],
        }
        candidates.append((len(best_tok), r["municipio"], info))
    if not candidates:
        # Sin coincidencia exacta de token, intenta un fallback DIFUSO (tolera typos:
        # "Medallin"→MEDELLÍN). Es conservador (ver constantes) para no arriesgar un municipio
        # equivocado, que daría un pronóstico confiado pero falso.
        return _fuzzy_municipio(qwords, resumen)
    candidates.sort(key=lambda c: -c[0])
    top_len = candidates[0][0]
    top = [c for c in candidates if c[0] == top_len]
    if len({c[1] for c in top}) > 1:  # mismo token máximo en municipios distintos → ambiguo
        return None
    return top[0][2]


def _fuzzy_municipio(qwords: set[str], resumen: pd.DataFrame) -> dict | None:
    """Casa el municipio por SIMILITUD (Levenshtein vía difflib) cuando falla el match exacto.

    Compara los tokens largos de la consulta contra los tokens largos de cada nombre oficial y se
    queda con el municipio de mayor similitud si supera el umbral. Si otro municipio distinto queda
    dentro del margen, se considera ambiguo y no se arriesga (devuelve None). Conservador por
    diseño: un falso positivo aquí produciría un pronóstico sobre el municipio equivocado.
    """
    qtokens = [w for w in qwords if len(w) >= _FUZZY_MIN_LEN]
    if not qtokens:
        return None
    scored: list[tuple[float, str, dict]] = []
    for _, r in resumen.iterrows():
        mtokens = [
            t for t in re.findall(r"[A-Z0-9]+", _norm(r["municipio"])) if len(t) >= _FUZZY_MIN_LEN
        ]
        ratio = 0.0
        for mt in mtokens:
            for qt in qtokens:
                ratio = max(ratio, difflib.SequenceMatcher(None, mt, qt).ratio())
        if ratio >= _FUZZY_CUTOFF:
            scored.append(
                (
                    ratio,
                    r["municipio"],
                    {
                        "cod_municipio": r["cod_municipio"],
                        "municipio": r["municipio"],
                        "departamento": r["departamento"],
                    },
                )
            )
    if not scored:
        return None
    scored.sort(key=lambda c: -c[0])
    best = scored[0]
    # Ambigüedad: otro municipio distinto casi empatado → no arriesgar.
    if any(c[1] != best[1] and best[0] - c[0] < _FUZZY_MARGIN for c in scored[1:]):
        return None
    log.info("Municipio casado por similitud difusa: %s (ratio %.2f)", best[1], best[0])
    return best[2]


def match_categoria(query: str, categorias: list[str]) -> str | None:
    """Casa la categoría mencionada usando palabras clave; si no hay, devuelve None."""
    q = _norm(query).lower()
    cats_norm = {_norm(c): c for c in categorias}
    for hint, target in _CATEGORY_HINTS.items():
        if hint in q:
            for cn, original in cats_norm.items():
                if _norm(target) in cn:
                    return original
    return None


def forecast_context(query: str, horizon: int = 6) -> dict | None:
    """Si la pregunta pide un pronóstico para un municipio reconocible, lo calcula y
    devuelve un fragmento de contexto (citable) con la proyección y su banda."""
    if not has_forecast_intent(query):
        return None
    try:
        resumen_path = settings.gold_dir / "resumen_municipio.parquet"
        serie_path = settings.gold_dir / "serie_mensual.parquet"
        if not resumen_path.exists() or not serie_path.exists():
            return None
        cols = ["cod_municipio", "municipio", "departamento"]
        resumen = pd.read_parquet(resumen_path, columns=cols)
        muni = match_municipio(query, resumen)
        if muni is None:
            return None

        from vigia.ml.forecasting import load_model, predict

        serie = pd.read_parquet(serie_path)
        sub = serie[serie["cod_municipio"] == muni["cod_municipio"]]
        if sub.empty:
            return None
        categoria = match_categoria(query, sorted(sub["categoria"].unique().tolist()))
        if categoria is None:
            # No se reconoció una categoría concreta en la pregunta. NO se asume la más
            # frecuente del municipio: eso daría un pronóstico confiado pero arbitrario
            # (p. ej. responder sobre HOMICIDIO cuando preguntaron por "asaltos"). Se
            # degrada al RAG clásico, que responde con las cifras históricas citadas.
            log.info("Pronóstico omitido: sin categoría reconocida en la consulta")
            return None

        model = load_model()
        pts = predict(serie, muni["cod_municipio"], categoria, horizon=horizon, model=model)
        if not pts:
            return None

        proj = "; ".join(
            f"{p['periodo']}: {p['prediccion']} "
            f"(rango {p.get('limite_inferior', '?')}–{p.get('limite_superior', '?')})"
            for p in pts
        )
        text = (
            f"Pronóstico del modelo VigIA para {categoria} en {muni['municipio']} "
            f"({muni['departamento']}), próximos {len(pts)} meses, "
            f"con banda de incertidumbre ~80%: "
            f"{proj}. Es una proyección estadística (ayuda a la decisión), no una certeza."
        )
        meta = {
            "tipo": "pronostico",
            "cod_municipio": muni["cod_municipio"],
            "categoria": categoria,
        }
        return {"content": text, "metadata": meta, "score": 1.0}
    except Exception as exc:  # noqa: BLE001 — degradación elegante a RAG clásico
        log.warning("Aumento híbrido de pronóstico omitido: %s", exc)
        return None
