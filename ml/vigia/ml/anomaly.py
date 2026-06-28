"""Detección de anomalías para alerta temprana.

Marca meses-municipio con incidencia atípica combinando dos señales:
1. z-score robusto (MAD) del residuo frente a la mediana móvil, calculado POR serie.
2. IsolationForest sobre [valor, residuo].
Se reporta anomalía al alza cuando AMBAS coinciden (consenso), reduciendo falsos positivos.

Solo se consideran categorías de **delito**: un repunte de la respuesta institucional
(capturas, incautaciones, recuperaciones) es una buena noticia operativa, no una alerta
de seguridad ciudadana, así que esas categorías se excluyen (ver datasets.RESPONSE_CATEGORIES).

Implementación vectorizada: las operaciones por grupo usan `groupby` en C y se ajusta
UN solo IsolationForest global, en vez de uno por serie (escala a miles de series).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from vigia.config import settings
from vigia.datasets import RESPONSE_CATEGORIES
from vigia.logging import get_logger

log = get_logger(__name__)

ROBUST_Z_THRESHOLD = 3.5
KEY = ["cod_municipio", "categoria"]
_COLS = [
    "cod_municipio",
    "municipio",
    "departamento",
    "categoria",
    "periodo",
    "cantidad",
    "score_z",
    "severidad",
]


def detect(
    series: pd.DataFrame,
    min_history: int = 18,
    contamination: float = 0.03,
    z_threshold: float = ROBUST_Z_THRESHOLD,
) -> pd.DataFrame:
    """Detecta anomalías por (municipio, categoría). Devuelve solo las anomalías al alza.

    `contamination` (proporción esperada de outliers del IsolationForest) y `z_threshold`
    (umbral del z robusto) son las dos perillas de CALIBRACIÓN del volumen de alertas: para
    un uso más operativo (menos alertas, más precisas) súbelas; para mayor sensibilidad,
    bájalas. Se exponen como parámetros para poder ajustarlas sin editar el código.

    El consenso de dos señales + el filtro de solo picos al alza mantienen la tasa real de
    alertas muy por debajo de `contamination`. Validado por precisión/recall contra picos
    inyectados (ver `tests/test_anomaly.py::test_benchmark_precision_recall_*`).
    """
    df = series.sort_values(KEY + ["periodo"]).copy()

    # Excluye las categorías de "respuesta institucional" (capturas, incautaciones,
    # recuperaciones): un pico al alza ahí es un buen resultado operativo, no una alerta
    # de seguridad. Mantenerlas marcaría en rojo en el tablero meses con MÁS capturas.
    df = df[~df["categoria"].isin(RESPONSE_CATEGORIES)]
    if df.empty:
        return pd.DataFrame(columns=_COLS)

    # Filtra series con poca historia (no se puede juzgar atipicidad de forma fiable)
    df["_n"] = df.groupby(KEY)["cantidad"].transform("size")
    df = df[df["_n"] >= min_history]
    if df.empty:
        return pd.DataFrame(columns=_COLS)

    y = df["cantidad"].astype(float)

    # Señal 1: residuo vs mediana móvil (12) por serie -> z robusto (mediana/MAD por grupo)
    roll = (
        df.groupby(KEY)["cantidad"]
        .rolling(12, min_periods=6)
        .median()
        .reset_index(level=KEY, drop=True)
    )
    roll = roll.fillna(df.groupby(KEY)["cantidad"].transform("median"))
    df["_roll"] = roll
    resid = y - df["_roll"]
    med = resid.groupby([df[k] for k in KEY]).transform("median")
    absdev = (resid - med).abs()
    mad = absdev.groupby([df[k] for k in KEY]).transform("median").replace(0, np.nan)
    df["_z"] = (0.6745 * (resid - med) / mad).fillna(0.0)
    sig_z = df["_z"].abs() > z_threshold

    # Señal 2: UN IsolationForest global sobre features YA NORMALIZADAS POR SERIE.
    # Usar [valor, residuo] crudos sesgaría el bosque hacia los municipios de mayor
    # volumen (Bogotá siempre parecería "outlier"); en su lugar se le pasa la atipicidad
    # *relativa* a cada serie: el z-robusto del residuo y el z-robusto del nivel.
    med_y = y.groupby([df[k] for k in KEY]).transform("median")
    mad_y = (y - med_y).abs().groupby([df[k] for k in KEY]).transform("median").replace(0, np.nan)
    z_nivel = (0.6745 * (y - med_y) / mad_y).fillna(0.0)
    feats = np.column_stack([df["_z"].to_numpy(), z_nivel.to_numpy()])
    iso = IsolationForest(contamination=contamination, random_state=settings.seed)
    sig_iso = iso.fit_predict(feats) == -1

    consenso = sig_z.to_numpy() & sig_iso & (y > df["_roll"]).to_numpy()  # solo picos al alza
    result = df.loc[consenso].copy()
    if result.empty:
        return pd.DataFrame(columns=_COLS)

    result["score_z"] = result["_z"].round(2)
    result["severidad"] = np.where(result["_z"].abs() > 5, "ALTA", "MEDIA")
    result = result[_COLS].sort_values("periodo", ascending=False).reset_index(drop=True)
    log.info("Anomalías detectadas: %d", len(result))
    return result


def run(series: pd.DataFrame) -> pd.DataFrame:
    """Detecta y persiste las anomalías en gold."""
    anomalies = detect(series)
    settings.ensure_dirs()
    anomalies.to_parquet(settings.gold_dir / "anomalias.parquet", index=False)
    return anomalies
