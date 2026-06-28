"""Simulación de escenarios "¿y si…?" sobre el pronóstico.

Capa contrafactual encima del modelo de pronóstico (`forecasting.predict`). Permite
explorar trayectorias alternativas moviendo palancas explícitas, separando con honestidad
la procedencia de cada una:

- **Palanca del MODELO** — un *shock de población* (migración, crecimiento, retorno): escala
  la población del municipio y el modelo re-deriva `log_poblacion` y reconvierte tasa→conteo.
  Es una respuesta genuina del modelo a una de sus features exógenas.
- **Palanca de SUPUESTO** — el efecto esperado de una *intervención* (un programa de seguridad):
  el modelo NO observa variables de política, así que el efecto lo aporta el usuario como un
  porcentaje de cambio de la incidencia, aplicado con una rampa temporal sobre la trayectoria
  servida. Se reporta etiquetado como supuesto del usuario, no como una estimación causal del
  modelo (no sobre-afirmar lo que los datos no soportan).

Un escenario sin palancas reproduce EXACTAMENTE el pronóstico base (`predict`): la simulación
no altera el modelo, solo proyecta supuestos sobre su salida. Toda la ruta degrada con
elegancia: sin historia o sin modelo devuelve None y el llamador decide.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from vigia.logging import get_logger
from vigia.ml.forecasting import ForecastModel, load_model, predict

log = get_logger(__name__)


@dataclass
class Scenario:
    """Palancas del escenario. Por defecto (todas en cero) ≡ pronóstico base.

    `intervencion_pct`: cambio porcentual esperado de la incidencia por una intervención
        (negativo = reducción; p. ej. -15 = "un programa que se espera reduzca 15% los hechos").
        Es un SUPUESTO del usuario, no un efecto estimado por el modelo.
    `ramp_meses`: meses hasta que la intervención alcanza su efecto pleno (0 = inmediato). Una
        política rara vez surte efecto total el primer mes; la rampa lineal modela su despliegue.
    `shock_poblacion_pct`: cambio porcentual de la población del municipio (exógeno). Fluye por el
        modelo (solo tiene efecto cuando el modelo opera en modo tasa, con población DANE).
    """

    intervencion_pct: float = 0.0
    ramp_meses: int = 0
    shock_poblacion_pct: float = 0.0

    def is_noop(self) -> bool:
        return self.intervencion_pct == 0.0 and self.shock_poblacion_pct == 0.0


def _ramp_weight(step: int, ramp_meses: int) -> float:
    """Peso de la rampa en `step` (1-indexado): 0→1 lineal en `ramp_meses`, luego 1.

    Con `ramp_meses<=0` el efecto es pleno desde el primer paso (peso 1).
    """
    if ramp_meses <= 0:
        return 1.0
    return min(1.0, step / ramp_meses)


def _apply_population_shock(series: pd.DataFrame, cod_municipio: str, pct: float) -> pd.DataFrame:
    """Copia de la serie con la población del municipio escalada en `pct`%.

    Solo se modifica la columna `poblacion` de ese municipio; el resto de la serie y los demás
    municipios quedan intactos. `predict` re-filtra internamente y recoge la población escalada,
    así que el shock fluye por las features (`log_poblacion`) y por la reconversión tasa→conteo
    sin tocar la recursión del modelo.
    """
    out = series.copy()
    # La población escalada por un % es float por naturaleza; si la columna viene como entero
    # (p. ej. Int64 nullable tras el reentrenamiento), asignar floats dispararía un error de cast
    # ("cannot safely cast ... to int64"). La normalizamos a float64 antes de escalar. `predict`
    # deriva log_poblacion de aquí, así que float es lo correcto más abajo.
    out["poblacion"] = pd.to_numeric(out["poblacion"], errors="coerce").astype("float64")
    mask = out["cod_municipio"] == cod_municipio
    out.loc[mask, "poblacion"] = out.loc[mask, "poblacion"] * (1.0 + pct / 100.0)
    return out


def simulate(
    series: pd.DataFrame,
    cod_municipio: str,
    categoria: str,
    scenario: Scenario,
    horizon: int = 6,
    model: ForecastModel | None = None,
) -> dict | None:
    """Compara el pronóstico base con un escenario contrafactual.

    Devuelve un dict con la trayectoria base, la del escenario, el delta por mes y el acumulado
    de hechos evitados/adicionales, o None si no hay historia/modelo. La incertidumbre de la
    trayectoria base se escala con el mismo factor de intervención (la banda acompaña a la media).
    """
    model = model or load_model()
    base = predict(series, cod_municipio, categoria, horizon=horizon, model=model)
    if not base:
        return None

    rate_mode = getattr(model, "target_mode", "count") == "rate"
    # Trayectoria del escenario: arranca del pronóstico base (o de uno re-derivado con el shock
    # de población si aplica y el modelo opera en tasa) y luego se le aplica la intervención.
    if scenario.shock_poblacion_pct and rate_mode and "poblacion" in series.columns:
        shocked = _apply_population_shock(series, cod_municipio, scenario.shock_poblacion_pct)
        traj = predict(shocked, cod_municipio, categoria, horizon=horizon, model=model)
        if not traj:
            traj = [dict(p) for p in base]
    else:
        if scenario.shock_poblacion_pct and not rate_mode:
            log.info(
                "Shock de población ignorado: el modelo no opera en modo tasa (sin población DANE)."
            )
        traj = [dict(p) for p in base]

    # Palanca de intervención (supuesto del usuario): factor multiplicativo con rampa sobre la
    # trayectoria servida. Se aplica a media y banda por igual para que el rango acompañe a la
    # proyección. clip a 0: una intervención no produce conteos negativos.
    factor_pct = scenario.intervencion_pct / 100.0
    for i, p in enumerate(traj, start=1):
        factor = 1.0 + factor_pct * _ramp_weight(i, scenario.ramp_meses)
        for key in ("prediccion", "limite_inferior", "limite_superior"):
            if p.get(key) is not None:
                p[key] = round(max(0.0, float(p[key]) * factor), 2)

    # Delta por mes y acumulado (positivo = hechos EVITADOS respecto al base).
    delta = []
    acum = 0.0
    for b, s in zip(base, traj, strict=True):
        evitados = round(b["prediccion"] - s["prediccion"], 2)
        acum = round(acum + evitados, 2)
        delta.append(
            {
                "periodo": b["periodo"],
                "base": b["prediccion"],
                "escenario": s["prediccion"],
                "evitados": evitados,
                "evitados_acumulado": acum,
            }
        )

    return {
        "cod_municipio": cod_municipio,
        "categoria": categoria,
        "horizonte": len(traj),
        "escenario": {
            "intervencion_pct": scenario.intervencion_pct,
            "ramp_meses": scenario.ramp_meses,
            "shock_poblacion_pct": scenario.shock_poblacion_pct,
        },
        "base": base,
        "proyeccion": traj,
        "delta": delta,
        "evitados_total": acum,
        # Procedencia de cada palanca (transparencia anti-sobreafirmación).
        "nota": (
            "La población es una palanca del modelo (re-deriva la tasa); la intervención es un "
            "supuesto del usuario sobre el efecto de una política, no una estimación causal del "
            "modelo. El escenario proyecta ese supuesto sobre el pronóstico base."
        ),
    }
