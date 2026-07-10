"""Ingeniería de features para el modelo global de pronóstico.

A partir de la serie mensual `municipio × categoria`, construye features de
rezago, medias móviles, estacionalidad (calendario) y tendencia, sin fuga de
datos (todas las features en t usan información disponible hasta t-1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LAGS = [1, 2, 3, 6, 12]
ROLL_WINDOWS = [3, 6, 12]
KEY = ["cod_municipio", "categoria"]
TARGET = "cantidad"
# Ventana (meses) de la media histórica de identidad (`media_hist`). NO es expansiva a
# propósito: sobre 20+ años, una media de TODA la historia arrastra el nivel de épocas
# superadas y tira el pronóstico hacia arriba en series con caída secular (p. ej. el
# homicidio de Medellín cayó ~90 % desde 2003: la media expansiva casi triplicaba su nivel
# actual y producía sobreestimaciones de +120 %). Con 60 meses la identidad de la serie se
# conserva (con `min_periods=1`, las series más cortas que la ventana obtienen exactamente
# su media expansiva) y el backtest mejora en MAE 1 paso, multipaso, MASE y el tercil alto
# (análisis de sensibilidad medido en la bitácora de docs/CRISP-ML-Q.md). No volver a la
# expansiva sin re-medir.
HIST_WINDOW = 60


def make_features(series: pd.DataFrame) -> pd.DataFrame:
    """Devuelve la serie con columnas de features añadidas (ordenada por periodo)."""
    df = series.sort_values(KEY + ["periodo"]).copy()
    g = df.groupby(KEY, dropna=False)[TARGET]

    for lag in LAGS:
        df[f"lag_{lag}"] = g.shift(lag)

    # Media/desviación móvil DENTRO de cada (municipio, categoría) sin fuga de datos.
    # `shift(1)` excluye el valor actual; usamos *grouped rolling* vectorizado (C) en
    # lugar de transform con lambdas de Python (orden de magnitud más rápido a escala).
    df["_t1"] = g.shift(1)
    gr = df.groupby(KEY, dropna=False)["_t1"]
    for w in ROLL_WINDOWS:
        df[f"roll_mean_{w}"] = gr.rolling(w).mean().reset_index(level=KEY, drop=True)
        df[f"roll_std_{w}"] = gr.rolling(w).std().reset_index(level=KEY, drop=True)

    # Identidad/escala de la serie: media de los últimos `HIST_WINDOW` valores PASADOS
    # (ver la nota del constante arriba: una media expansiva sobre 20+ años arrastra épocas
    # superadas y sobreestima las series con caída secular) y nº de observaciones previas.
    # Dan al modelo global el nivel base propio de cada (municipio, categoría) —p. ej.
    # distinguir homicidios en Bogotá de un hurto en un municipio pequeño— sin fuga de
    # datos (ambas excluyen el valor en t: la media opera sobre el target desplazado).
    df["media_hist"] = (
        gr.rolling(HIST_WINDOW, min_periods=1).mean().reset_index(level=KEY, drop=True)
    )
    df = df.drop(columns="_t1")
    gpast = df.groupby(KEY, dropna=False)[TARGET]
    df["meses_activos"] = gpast.cumcount().astype("float64")

    # Población (DANE) como señal EXÓGENA: da al modelo la escala demográfica real del
    # municipio (mejor que el proxy `media_hist`) y, vía `tasa_hist`, la incidencia POR
    # 100.000 habitantes —comparable entre Bogotá y un municipio pequeño—. Es la primera
    # feature no autorregresiva del pronóstico. Sin fuga: la población es una proyección
    # exógena conocida de antemano; `tasa_hist` usa solo el pasado (media_hist).
    if "poblacion" in df.columns:
        pob = pd.to_numeric(df["poblacion"], errors="coerce")
        df["log_poblacion"] = np.log1p(pob)
        df["tasa_hist"] = df["media_hist"] / pob.where(pob > 0) * 1e5

    # Estacionalidad y calendario
    df["mes"] = df["periodo"].dt.month
    df["trimestre"] = df["periodo"].dt.quarter
    df["mes_sin"] = np.sin(2 * np.pi * df["mes"] / 12)
    df["mes_cos"] = np.cos(2 * np.pi * df["mes"] / 12)
    # Índice de tendencia (meses desde el inicio de la serie global)
    df["trend"] = (df["periodo"].dt.year - df["periodo"].dt.year.min()) * 12 + df[
        "periodo"
    ].dt.month

    return df


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Columnas numéricas usadas como entrada del modelo."""
    cols = [c for c in df.columns if c.startswith(("lag_", "roll_"))]
    cols += ["media_hist", "meses_activos", "mes", "trimestre", "mes_sin", "mes_cos", "trend"]
    # Features exógenas de población (solo si la serie las trae; degradación elegante).
    cols += [c for c in ("log_poblacion", "tasa_hist") if c in df.columns]
    return cols
