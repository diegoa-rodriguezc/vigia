"""API FastAPI del servicio ML de VigIA.

Expone los componentes de IA (pronóstico, anomalías, RAG) para que el backend Go
los consuma. Carga perezosa de artefactos (modelo, datos gold) en memoria.
"""

from __future__ import annotations

import pandas as pd
from fastapi import FastAPI, HTTPException

from vigia.api.schemas import (
    AnomalyItem,
    BriefResponse,
    ChatRequest,
    ChatResponse,
    PredictRequest,
    PredictResponse,
    SimulateRequest,
    SimulateResponse,
)
from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)

app = FastAPI(
    title="VigIA — Servicio ML",
    description="Pronósticos de criminalidad, detección de anomalías y asistente RAG ciudadano.",
    version="0.1.0",
)


# Caché de la serie gold invalidado por la marca de tiempo del archivo: si el pipeline
# se re-ejecuta (nuevas categorías/datos), el API recarga sin reiniciar el contenedor.
# Un lru_cache simple dejaba la serie "congelada" y el pronóstico ignoraba lo nuevo.
_series_cache: dict = {"mtime": None, "df": None}


def _series() -> pd.DataFrame:
    path = settings.gold_dir / "serie_mensual.parquet"
    if not path.exists():
        raise RuntimeError("Datos gold ausentes. Ejecute el pipeline ETL.")
    mtime = path.stat().st_mtime
    if _series_cache["mtime"] != mtime:
        _series_cache["df"] = pd.read_parquet(path)
        _series_cache["mtime"] = mtime
        log.info(
            "Serie mensual de la capa gold cargada: %d filas, %d categorías",
            len(_series_cache["df"]),
            _series_cache["df"]["categoria"].nunique(),
        )
    return _series_cache["df"]


@app.get("/health")
def health() -> dict:
    """Estado del servicio y disponibilidad de artefactos."""
    from vigia.db import ping
    from vigia.ml.forecasting import MODEL_PATH

    return {
        "status": "ok",
        "modelo_entrenado": MODEL_PATH.exists(),
        "gold_disponible": (settings.gold_dir / "serie_mensual.parquet").exists(),
        "db": ping(),
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    """Pronóstico de criminalidad por municipio y categoría."""
    from vigia.ml.forecasting import predict as forecast

    try:
        pts = forecast(_series(), req.cod_municipio, req.categoria, req.horizon)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not pts:
        raise HTTPException(status_code=404, detail="Sin historia para ese municipio/categoría.")
    return PredictResponse(
        cod_municipio=req.cod_municipio,
        categoria=req.categoria,
        horizonte=req.horizon,
        pronostico=pts,
    )


@app.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest) -> SimulateResponse:
    """Simulación de escenarios "¿y si…?": proyecta una intervención y/o un shock de población
    sobre el pronóstico base y reporta los hechos evitados acumulados."""
    from vigia.ml.simulation import Scenario
    from vigia.ml.simulation import simulate as run_sim

    scenario = Scenario(
        intervencion_pct=req.intervencion_pct,
        ramp_meses=req.ramp_meses,
        shock_poblacion_pct=req.shock_poblacion_pct,
    )
    try:
        res = run_sim(_series(), req.cod_municipio, req.categoria, scenario, horizon=req.horizon)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if res is None:
        raise HTTPException(status_code=404, detail="Sin historia para ese municipio/categoría.")
    return SimulateResponse(**res)


@app.get("/monitoring")
def monitoring() -> dict:
    """Reporte de salud del modelo (frescura de datos, deriva/PSI, backtest extendido).

    Devuelve el artefacto reproducible `reports/model_health.json` que genera `vigia health`.
    """
    import json

    path = settings.reports_dir / "model_health.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Sin reporte de salud. Ejecute `vigia health`.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/anomalies", response_model=list[AnomalyItem])
def anomalies(limit: int = 50) -> list[AnomalyItem]:
    """Anomalías detectadas (alertas tempranas) más recientes."""
    path = settings.gold_dir / "anomalias.parquet"
    if not path.exists():
        return []
    df = pd.read_parquet(path).head(limit).copy()
    df["periodo"] = pd.to_datetime(df["periodo"]).dt.strftime("%Y-%m")
    return [AnomalyItem(**row) for row in df.to_dict(orient="records")]


@app.get("/brief/{cod_municipio}", response_model=BriefResponse)
def brief(cod_municipio: str) -> BriefResponse:
    """Informe ejecutivo de seguridad de un municipio (IA generativa anclada a datos)."""
    from vigia.rag.brief import generate_brief

    try:
        res = generate_brief(cod_municipio)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Generación no disponible: {exc}") from exc
    if res is None:
        raise HTTPException(status_code=404, detail="Sin datos para ese municipio.")
    return BriefResponse(**res.__dict__)


@app.post("/rag/chat", response_model=ChatResponse)
def rag_chat(req: ChatRequest) -> ChatResponse:
    """Asistente ciudadano sobre datos oficiales.

    Usa el AGENTE con herramientas si el proveedor LLM lo soporta (Anthropic/OpenAI); si no,
    cae al RAG clásico. La decisión vive en `rag.agent.answer` (transparente para el backend).
    """
    from vigia.rag.agent import answer

    try:
        res = answer(req.pregunta)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Asistente no disponible: {exc}") from exc
    return ChatResponse(respuesta=res.answer, fuentes=res.sources, modo=res.modo, pasos=res.steps)
