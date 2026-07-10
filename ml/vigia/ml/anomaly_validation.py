"""Validación de las anomalías detectadas.

El benchmark de `tests/test_anomaly.py` mide precisión/recall contra picos INYECTADOS (ground
truth sintético). Este módulo aporta dos validaciones complementarias sobre las anomalías REALES,
pensadas para la ausencia de una verdad-terreno oficial (no hay contacto con entidades):

1. **Contra un catálogo de eventos documentados** (`validate_against_events`): el usuario aporta un
   archivo con hitos reales y públicos (un homicidio masivo, un paro, una asonada…) con su municipio
   y mes; se mide qué fracción de esos hitos cayó cerca (±ventana) de una anomalía detectada
   (recall@ventana). El catálogo es un INSUMO externo y parametrizable —no hechos quemados en el
   código— para que se pueda ampliar/auditar sin tocar el software.
2. **Corroboración interna** (`corroboration`), sin datos externos: ¿qué fracción de las anomalías
   está respaldada por OTRA categoría de delito en el mismo municipio-mes? Un deterioro real de la
   seguridad suele afectar varios delitos a la vez; un artefacto de datos aislado, no. Es una señal
   de *validez de cara* que no requiere verdad-terreno.

Ambas degradan con elegancia (catálogo ausente/vacío → solo corroboración).
"""

from __future__ import annotations

import pandas as pd

from vigia.logging import get_logger

log = get_logger(__name__)

# Columnas mínimas que debe traer el catálogo de eventos documentados.
EVENT_COLS = ("cod_municipio", "periodo")


def _to_month(s: pd.Series) -> pd.Series:
    """Normaliza una columna de periodo a marca de tiempo del primer día del mes."""
    return pd.to_datetime(s, errors="coerce").dt.to_period("M").dt.to_timestamp()


def validate_against_events(
    anomalies: pd.DataFrame,
    events: pd.DataFrame,
    window_months: int = 1,
    by_categoria: bool = False,
) -> dict:
    """Mide qué eventos documentados fueron capturados por una anomalía (recall@ventana).

    Un evento se considera *detectado* si existe una anomalía en el MISMO municipio (y la misma
    categoría, si `by_categoria` y el evento la trae) dentro de ±`window_months` meses. La ventana
    absorbe el desfase entre el hecho y su registro/consolidación administrativa.
    """
    faltan = [c for c in EVENT_COLS if c not in events.columns]
    if faltan:
        raise ValueError(f"El catálogo de eventos requiere columnas {EVENT_COLS}; faltan {faltan}.")
    if anomalies.empty or events.empty:
        return {
            "n_eventos": int(len(events)),
            "n_detectados": 0,
            "recall": 0.0,
            "window_months": window_months,
            "by_categoria": by_categoria,
            "detalle": [],
        }

    an = anomalies.copy()
    an["_m"] = _to_month(an["periodo"])
    ev = events.copy()
    ev["_m"] = _to_month(ev["periodo"])
    tiene_cat_ev = "categoria" in ev.columns

    detalle = []
    for _, e in ev.iterrows():
        cand = an[an["cod_municipio"].astype(str) == str(e["cod_municipio"])]
        if by_categoria and tiene_cat_ev and pd.notna(e.get("categoria")):
            cand = cand[cand["categoria"] == e["categoria"]]
        # Diferencia en meses entre el evento y cada anomalía candidata.
        if not cand.empty and pd.notna(e["_m"]):
            meses = (cand["_m"].dt.year - e["_m"].year) * 12 + (cand["_m"].dt.month - e["_m"].month)
            hit = bool((meses.abs() <= window_months).any())
        else:
            hit = False
        detalle.append(
            {
                "cod_municipio": str(e["cod_municipio"]),
                "periodo": e["_m"].strftime("%Y-%m") if pd.notna(e["_m"]) else None,
                "categoria": e.get("categoria") if tiene_cat_ev else None,
                "descripcion": e.get("descripcion"),
                "detectado": hit,
            }
        )
    n_det = sum(d["detectado"] for d in detalle)
    n = len(detalle)
    return {
        "n_eventos": n,
        "n_detectados": int(n_det),
        "recall": round(n_det / n, 3) if n else 0.0,
        "window_months": window_months,
        "by_categoria": by_categoria,
        "detalle": detalle,
    }


def corroboration(anomalies: pd.DataFrame) -> dict:
    """Validez interna: fracción de anomalías corroboradas por otra categoría en el mismo
    municipio-mes (sin verdad-terreno externa).

    Agrupa por (municipio, mes) y cuenta categorías distintas con anomalía: una anomalía está
    *corroborada* si su municipio-mes registra ≥2 categorías de delito atípicas a la vez. Reportar
    esta fracción da evidencia de que las alertas reflejan deterioros reales (multidelito) y no
    blips aislados. NO es prueba causal; es una señal agregada de validez de cara.
    """
    if anomalies.empty:
        return {
            "n_anomalias": 0,
            "n_corroboradas": 0,
            "fraccion_corroborada": 0.0,
            "n_clusters_multidelito": 0,
        }
    an = anomalies.copy()
    an["_m"] = _to_month(an["periodo"])
    # Categorías distintas por municipio-mes.
    ncat = an.groupby(["cod_municipio", "_m"])["categoria"].transform("nunique")
    corroboradas = int((ncat >= 2).sum())
    n = len(an)
    clusters = int(an[ncat >= 2].groupby(["cod_municipio", "_m"]).ngroups)
    return {
        "n_anomalias": n,
        "n_corroboradas": corroboradas,
        "fraccion_corroborada": round(corroboradas / n, 3) if n else 0.0,
        "n_clusters_multidelito": clusters,
    }


def write_report(
    anomalies: pd.DataFrame,
    events: pd.DataFrame | None = None,
    window_months: int = 1,
) -> dict:
    """Ejecuta la validación y la persiste en `reports/anomaly_validation.json` (reproducible).

    Para no sobrevender los "aciertos" triviales de municipios grandes (donde casi todo mes tiene
    *alguna* anomalía), el reporte emite **ambos** modos: `contra_eventos_documentados` casa por
    municipio-mes, y `contra_eventos_documentados_por_categoria` exige además que la anomalía
    coincida en categoría (HOMICIDIO, TERRORISMO…) — una validación más estricta y específica.
    """
    import json

    from vigia.config import settings

    report: dict = {
        # Corte del dato validado — fecha derivada del DATO, no reloj de pared: así el reporte
        # de una misma ejecución del pipeline se reproduce byte a byte (linaje auditable).
        "corte_dato": (
            pd.to_datetime(anomalies["periodo"]).max().strftime("%Y-%m") if len(anomalies) else None
        ),
        "n_anomalias": int(len(anomalies)),
        "corroboracion_interna": corroboration(anomalies),
    }
    if events is not None and not events.empty:
        report["contra_eventos_documentados"] = validate_against_events(
            anomalies, events, window_months=window_months, by_categoria=False
        )
        report["contra_eventos_documentados_por_categoria"] = validate_against_events(
            anomalies, events, window_months=window_months, by_categoria=True
        )
    else:
        report["contra_eventos_documentados"] = None
        report["contra_eventos_documentados_por_categoria"] = None
        log.info("Sin catálogo de eventos documentados: solo se reporta la corroboración interna.")

    settings.ensure_dirs()
    path = settings.reports_dir / "anomaly_validation.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Reporte de validación de anomalías guardado en %s", path)
    return report
