"""CLI de VigIA (Typer) — orquesta el pipeline CRISP-ML(Q).

Uso: `vigia <comando>` o `python -m vigia <comando>`.
"""

from __future__ import annotations

import typer

from vigia.logging import get_logger

app = typer.Typer(add_completion=False, help="VigIA — pipeline de datos, ML y RAG.")
log = get_logger(__name__)


@app.command()
def ingest(only: list[str] = typer.Option(None, help="Ingerir solo estos dataset ids")) -> None:
    """Descarga los datos abiertos (SODA2) a la capa bronze."""
    from vigia.etl.bronze import ingest_all

    ingest_all(only=only or None)


@app.command()
def clean() -> None:
    """Limpia y unifica las fuentes a la capa silver."""
    from vigia.etl.silver import build_silver

    build_silver()


@app.command()
def gold() -> None:
    """Genera los agregados y features de la capa gold."""
    from vigia.etl.gold import build_gold

    build_gold()


def _run_training(test_months: int = 6):
    """Lógica de entrenamiento reutilizable (no es un comando Typer)."""
    import pandas as pd

    from vigia.config import settings
    from vigia.ml import anomaly, evaluate, forecasting

    series = pd.read_parquet(settings.gold_dir / "serie_mensual.parquet")
    model = forecasting.train(series, test_months=test_months)
    log.info("Métricas backtest: %s", model.metrics)
    anomaly.run(series)
    # Persiste el reporte reproducible (fase de evaluación CRISP-ML(Q)).
    evaluate.write_model_report(series, model)
    return model


@app.command()
def train(test_months: int = 6) -> None:
    """Entrena el modelo de pronóstico y ejecuta la detección de anomalías."""
    _run_training(test_months=test_months)


@app.command(name="load-db")
def load_db() -> None:
    """Carga los artefactos gold a PostgreSQL (tablas servidas por el backend Go)."""
    from vigia.etl.load import load_gold

    load_gold()


@app.command(name="rag-index")
def rag_index() -> None:
    """Construye el índice del asistente RAG en pgvector."""
    from vigia.rag.ingest import build_index

    n = build_index()
    typer.echo(f"Fragmentos indexados: {n}")


@app.command()
def pipeline() -> None:
    """Ejecuta el pipeline completo:
    ingest -> clean -> gold -> justicia -> train -> validate-anomalies -> load-db -> rag-index.

    Llama a las funciones de librería directamente (no a los comandos Typer, que pasarían
    objetos OptionInfo en vez de los valores por defecto).
    """
    from vigia.etl.bronze import ingest_all
    from vigia.etl.gold import build_gold
    from vigia.etl.load import load_gold
    from vigia.etl.silver import build_silver
    from vigia.rag.ingest import build_index

    ingest_all()
    build_silver()
    build_gold()
    _build_justicia_layer()
    _run_training()
    _validate_anomalies_against_catalog()
    for step, fn in (("load-db", load_gold), ("rag-index", build_index)):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — requieren BD/LLM disponibles
            log.warning("%s omitido (¿BD/Ollama arriba?): %s", step, exc)


def _build_justicia_layer() -> None:
    """Construye la capa Justicia (gold + reporte) si su bronze está disponible; skip elegante."""
    try:
        from vigia.etl.justicia import build_justicia

        build_justicia()
    except Exception as exc:  # noqa: BLE001 — no debe tumbar el pipeline si falta el bronze
        log.warning("Capa Justicia omitida: %s", exc)


def _validate_anomalies_against_catalog() -> None:
    """Valida las anomalías contra el catálogo de eventos documentados (si existe).

    Reproducible dentro del pipeline: regenera `reports/anomaly_validation.json` con el recall
    real. Degrada con elegancia si el catálogo no está montado (solo corroboración interna)."""
    import pandas as pd

    from vigia.config import settings
    from vigia.ml import anomaly_validation as av

    try:
        anomalies = pd.read_parquet(settings.gold_dir / "anomalias.parquet")
        cat = settings.events_catalog
        ev = pd.read_csv(cat, dtype={"cod_municipio": str}, comment="#") if cat.exists() else None
        if ev is None:
            log.info("validate-anomalies: catálogo %s no encontrado → solo corroboración", cat)
        av.write_report(anomalies, events=ev)
    except Exception as exc:  # noqa: BLE001 — no debe tumbar el pipeline
        log.warning("validate-anomalies omitido: %s", exc)


@app.command()
def justicia() -> None:
    """Construye la capa "Justicia" (procesos de la Fiscalía): gold + tasa de judicialización.

    Requiere el bronze agregado (`vigia ingest --only justicia_procesos`). Escribe
    `gold/justicia_anual.parquet`, `gold/justicia_resumen.parquet` y `reports/justicia.json`."""
    from vigia.etl.justicia import build_justicia

    build_justicia()
    import json

    from vigia.config import settings

    rep = json.loads((settings.reports_dir / "justicia.json").read_text(encoding="utf-8"))
    typer.echo(
        f"Justicia: {rep['total_procesos']:,} procesos · "
        f"tasa de judicialización nacional {rep['tasa_judicializacion_nacional_pct']}% · "
        f"{rep['cobertura']['municipios']} municipios ({rep['cobertura']['anio_min']}–"
        f"{rep['cobertura']['anio_max']})."
    )


@app.command()
def challenger(test_months: int = 6) -> None:
    """Compara el modelo en producción (HGB) con un challenger neuronal (MLP) bajo el mismo
    backtest sin fuga. Solo evalúa y reporta (no cambia el modelo servido)."""
    import pandas as pd

    from vigia.config import settings
    from vigia.ml import challenger as ch

    series = pd.read_parquet(settings.gold_dir / "serie_mensual.parquet")
    report = ch.write_report(series, test_months=test_months)
    typer.echo(report["veredicto"])


@app.command(name="validate-anomalies")
def validate_anomalies(
    events: str = typer.Option(
        None,
        help="CSV de eventos documentados (def: settings.events_catalog)",
    ),
    window: int = typer.Option(1, help="Ventana ± en meses para casar un evento con una anomalía"),
) -> None:
    """Valida las anomalías detectadas: corroboración interna (multi-delito) y, si se aporta un
    catálogo de eventos documentados, recall@ventana contra esos hitos reales (dos modos)."""
    import pandas as pd

    from vigia.config import settings
    from vigia.ml import anomaly_validation as av

    anomalies = pd.read_parquet(settings.gold_dir / "anomalias.parquet")
    # Por defecto usa el catálogo versionado; `comment="#"` permite anotarlo/encabezarlo.
    src = events or (str(settings.events_catalog) if settings.events_catalog.exists() else None)
    ev = pd.read_csv(src, dtype={"cod_municipio": str}, comment="#") if src else None
    report = av.write_report(anomalies, events=ev, window_months=window)
    corr = report["corroboracion_interna"]
    typer.echo(
        f"Corroboración interna: {corr['fraccion_corroborada']:.1%} de {corr['n_anomalias']} "
        f"anomalías respaldadas por otra categoría en el mismo municipio-mes "
        f"({corr['n_clusters_multidelito']} clústeres multi-delito)."
    )
    mm = report["contra_eventos_documentados"]
    cat = report["contra_eventos_documentados_por_categoria"]
    if mm:
        typer.echo(
            f"Eventos documentados (±{mm['window_months']} mes): recall por municipio-mes "
            f"{mm['recall']:.1%} ({mm['n_detectados']}/{mm['n_eventos']}); "
            f"exigiendo categoría {cat['recall']:.1%} ({cat['n_detectados']}/{cat['n_eventos']})."
        )


@app.command()
def health(horizon: int = 12) -> None:
    """Reporte de salud del modelo: frescura de datos, deriva (PSI) y backtest extendido a
    `horizon` meses. Solo observa (no reentrena). Escribe reports/model_health.json."""
    import pandas as pd

    from vigia.config import settings
    from vigia.ml import monitoring

    series = pd.read_parquet(settings.gold_dir / "serie_mensual.parquet")
    rep = monitoring.write_report(series, horizon=horizon)
    fr, dr, bt = rep["frescura"], rep["deriva_datos"], rep["backtest_extendido"]
    fe, de = fr["estado"], dr["estado"]
    typer.echo(f"Estado global: {rep['estado_global'].upper()}")
    typer.echo(f"  Frescura [{fe}]: rezago {fr['lag_meses']} mes(es), datos a {fr['periodo_max']}")
    typer.echo(f"  Deriva [{de}]: PSI={dr['psi']}, cambio volumen {dr.get('cambio_volumen_pct')}%")
    if bt:
        supera = "supera" if bt["supera_baseline_mae"] else "no supera"
        typer.echo(
            f"  Backtest h={bt['horizon']}: MAE {bt['mae']} vs base {bt['baseline_mae']} "
            f"({supera} la persistencia) — {bt['estado']}"
        )


@app.command()
def ask(pregunta: str) -> None:
    """Consulta al asistente ciudadano desde la terminal (agente con herramientas si el proveedor
    LLM lo soporta; si no, RAG clásico)."""
    from vigia.rag.agent import answer

    res = answer(pregunta)
    typer.echo(res.answer)


@app.command()
def brief(
    municipio: str = typer.Argument(
        ..., help="Código DANE o nombre del municipio (p. ej. 76001 o Cali)"
    ),
) -> None:
    """Genera un informe ejecutivo de seguridad para un municipio (IA generativa anclada a datos:
    panorama, alertas, pronóstico y judicialización)."""
    from vigia.rag import tools
    from vigia.rag.brief import generate_brief

    cod = municipio.strip()
    if not cod.isdigit():  # se recibió un nombre → resolver al código DANE oficial
        res = tools.execute("resolver_municipio", {"texto": cod})
        if not res.get("encontrado"):
            typer.echo(f"No se reconoció el municipio: {municipio}")
            raise typer.Exit(code=1)
        cod = res["cod_municipio"]

    result = generate_brief(cod)
    if result is None:
        typer.echo("Sin datos para ese municipio. ¿Ejecutaste el pipeline?")
        raise typer.Exit(code=1)
    typer.echo(
        f"# Informe de seguridad — {result.municipio} "
        f"({result.departamento})  [{result.generado}]\n"
    )
    typer.echo(result.informe)


if __name__ == "__main__":
    app()
