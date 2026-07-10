"""CLI de VigIA (Typer) — orquesta el pipeline CRISP-ML(Q).

Uso: `vigia <comando>` o `python -m vigia <comando>`.
"""

from __future__ import annotations

import typer

from vigia.logging import get_logger

app = typer.Typer(add_completion=False, help="VigIA — pipeline de datos, ML y RAG.")
log = get_logger(__name__)


def _miles(n: float) -> str:
    """Entero con separador de miles al estilo es-CO (punto): 23029390 → '23.029.390'."""
    return f"{int(n):,}".replace(",", ".")


def _pct(v: float | None, dec: int = 1, *, de_fraccion: bool = False) -> str:
    """Porcentaje es-CO: coma decimal y espacio antes del símbolo ('8,51 %'). Con
    `de_fraccion`, escala una fracción 0-1 a porcentaje (0.233 → '23,3 %')."""
    if v is None:
        return "n/d"
    x = v * 100 if de_fraccion else v
    return f"{x:.{dec}f}".replace(".", ",") + " %"


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
    """Carga los artefactos gold a PostgreSQL (las tablas que expone el backend Go)."""
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
        f"Justicia: {_miles(rep['total_procesos'])} procesos · "
        f"tasa de judicialización nacional {_pct(rep['tasa_judicializacion_nacional_pct'], 2)} · "
        f"{rep['cobertura']['municipios']} municipios ({rep['cobertura']['anio_min']}–"
        f"{rep['cobertura']['anio_max']})."
    )


@app.command()
def challenger(test_months: int = 6) -> None:
    """Compara el modelo en producción (HGB) con un challenger neuronal (MLP) bajo el mismo
    backtest sin fuga. Solo evalúa y reporta (no cambia el modelo en producción)."""
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
    """Valida las anomalías detectadas: corroboración interna (multidelito) y, si se aporta un
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
    frac = _pct(corr["fraccion_corroborada"], 1, de_fraccion=True)
    typer.echo(
        f"Corroboración interna: {frac} de {corr['n_anomalias']} "
        f"anomalías respaldadas por otra categoría en el mismo municipio-mes "
        f"({corr['n_clusters_multidelito']} clústeres multidelito)."
    )
    mm = report["contra_eventos_documentados"]
    cat = report["contra_eventos_documentados_por_categoria"]
    if mm:
        r_muni = _pct(mm["recall"], 1, de_fraccion=True)
        r_cat = _pct(cat["recall"], 1, de_fraccion=True)
        typer.echo(
            f"Eventos documentados (±{mm['window_months']} mes): recall por municipio-mes "
            f"{r_muni} ({mm['n_detectados']}/{mm['n_eventos']}); "
            f"exigiendo categoría {r_cat} ({cat['n_detectados']}/{cat['n_eventos']})."
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
    _mes = "mes" if fr["lag_meses"] == 1 else "meses"
    typer.echo(f"  Frescura [{fe}]: rezago {fr['lag_meses']} {_mes}, datos a {fr['periodo_max']}")
    _cv = dr.get("cambio_volumen_pct")
    typer.echo(
        f"  Deriva [{de}]: PSI={str(dr['psi']).replace('.', ',')}, "
        f"cambio volumen {_pct(_cv, 1) if _cv is not None else 'n/d'}"
    )
    if bt:
        supera = "supera" if bt["supera_baseline_mae"] else "no supera"
        typer.echo(
            f"  Backtest h={bt['horizon']}: MAE {bt['mae']} vs base {bt['baseline_mae']} "
            f"({supera} la persistencia) — {bt['estado']}"
        )


@app.command(name="rag-eval")
def rag_eval(
    modo: str = typer.Option(
        "auto",
        help=(
            "Camino a evaluar: auto (producción: agente si el proveedor admite "
            "herramientas, si no RAG clásico) | agente | clasico. Funciona con ambos "
            "proveedores (openai/anthropic → agente; Ollama local → clásico, más lento)."
        ),
    ),
    out: str = typer.Option(
        "rag_eval.json",
        help=(
            "Nombre del archivo de salida (dentro de reports/). Permite versionar la "
            "medición de varios caminos, p. ej. rag_eval_ollama.json para el camino "
            "por defecto, sin sobrescribir el reporte del agente."
        ),
    ),
) -> None:
    """Evalúa el asistente con preguntas de referencia DERIVADAS de gold/reports (no quemadas):
    exactitud de cifras, abstención ante lo fuera de alcance (guardarraíl medido), citación
    de fuentes y resolución de municipios con errores de tipeo. Requiere BD + proveedor LLM
    activos; escribe reports/<out> (por defecto rag_eval.json)."""
    from vigia.rag import evaluation

    rep = evaluation.write_report(modo=modo, out_name=out)
    pct = lambda v: _pct(v, 0, de_fraccion=True) if v is not None else "n/d"  # noqa: E731
    typer.echo(
        f"Asistente evaluado ({rep['n_preguntas']} preguntas, modo {rep['modo_efectivo']}): "
        f"exactitud de cifras {pct(rep['exactitud_cifras'])} · "
        f"abstención correcta {pct(rep['abstencion_correcta'])} · "
        f"citación en aciertos {pct(rep['citacion_en_aciertos'])} · "
        f"latencia media {rep['latencia_media_s']} s"
    )
    fallos = [d["id"] for d in rep["detalle"] if not d.get("acierto")]
    if fallos:
        typer.echo(f"Fallos: {', '.join(fallos)} (detalle en reports/{out})")


@app.command()
def ask(pregunta: str) -> None:
    """Consulta al asistente ciudadano desde la terminal (agente con herramientas si el proveedor
    LLM lo admite; si no, RAG clásico)."""
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
        typer.echo("Sin datos para ese municipio. ¿Ejecutó el pipeline?")
        raise typer.Exit(code=1)
    typer.echo(
        f"# Informe de seguridad — {result.municipio} "
        f"({result.departamento})  [{result.generado}]\n"
    )
    typer.echo(result.informe)


if __name__ == "__main__":
    app()
