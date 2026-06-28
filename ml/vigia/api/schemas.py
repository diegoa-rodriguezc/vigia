"""Esquemas Pydantic de entrada/salida del servicio ML."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    cod_municipio: str = Field(..., examples=["11001"])
    categoria: str = Field(..., examples=["HOMICIDIO"])
    horizon: int = Field(6, ge=1, le=24)


class PredictPoint(BaseModel):
    periodo: str
    prediccion: float
    limite_inferior: float | None = None  # banda de incertidumbre (~80%)
    limite_superior: float | None = None


class PredictResponse(BaseModel):
    cod_municipio: str
    categoria: str
    horizonte: int
    pronostico: list[PredictPoint]


class SimulateRequest(BaseModel):
    cod_municipio: str = Field(..., examples=["11001"])
    categoria: str = Field(..., examples=["HOMICIDIO"])
    horizon: int = Field(6, ge=1, le=24)
    # Efecto esperado de una intervención (supuesto del usuario), en % de cambio de la incidencia.
    intervencion_pct: float = Field(0.0, ge=-100, le=100, examples=[-15])
    ramp_meses: int = Field(0, ge=0, le=24, examples=[3])
    # Shock exógeno de población (% de cambio); fluye por el modelo (solo en modo tasa).
    shock_poblacion_pct: float = Field(0.0, ge=-100, le=100, examples=[5])


class SimulateDeltaPoint(BaseModel):
    periodo: str
    base: float
    escenario: float
    evitados: float
    evitados_acumulado: float


class SimulateResponse(BaseModel):
    cod_municipio: str
    categoria: str
    horizonte: int
    escenario: dict
    base: list[PredictPoint]
    proyeccion: list[PredictPoint]
    delta: list[SimulateDeltaPoint]
    evitados_total: float
    nota: str


class AnomalyItem(BaseModel):
    cod_municipio: str
    municipio: str
    departamento: str
    categoria: str
    periodo: str
    cantidad: int
    score_z: float
    severidad: str


class ChatRequest(BaseModel):
    pregunta: str = Field(..., examples=["¿Cuáles son los delitos más frecuentes en Medellín?"])
    k: int = Field(5, ge=1, le=10)


class Source(BaseModel):
    content: str
    metadata: dict
    score: float


class ChatResponse(BaseModel):
    respuesta: str
    fuentes: list[Source]
