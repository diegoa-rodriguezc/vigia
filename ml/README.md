# Servicio ML — Datos, Modelos y RAG (Python)

Núcleo de ciencia de datos de VigIA: ingesta de datos abiertos, ETL medallion, modelos de IA y
asistente RAG, expuestos vía una API FastAPI.

## Instalación

```bash
pip install -e ".[dev]"          # núcleo + herramientas de desarrollo
pip install -e ".[rag-local]"    # opcional: embeddings locales (sentence-transformers)
```

## Pipeline (CRISP-ML(Q))

```bash
vigia ingest      # SODA2 (datos.gov.co) -> data/bronze
vigia clean       # limpieza + unificación de esquemas -> data/silver/eventos.parquet
vigia gold        # agregados + features -> data/gold
vigia justicia    # capa paralela Fiscalía (embudo de judicialización) -> data/gold
vigia train       # forecasting + anomalías -> models/
vigia load-db     # carga gold a PostgreSQL
vigia rag-index   # construye el índice del asistente en pgvector (data cards + docs)
# o todo de una vez:
vigia pipeline

# comandos de monitoreo/evaluación (offline, no parte del pipeline):
vigia health             # salud del modelo (frescura, deriva PSI, backtest 12m)
vigia challenger         # champion (HGB) vs challenger neuronal (MLP) — solo evaluación
vigia validate-anomalies # validación de anomalías reales (recall + corroboración)

# comandos de consulta directa (CLI, sin levantar la API):
vigia brief <cod_municipio>  # informe ejecutivo municipal (IA generativa anclada)
vigia ask "<pregunta>"       # pregunta al asistente RAG desde la terminal
```

## API

```bash
uvicorn vigia.api.main:app --reload --port 8000   # http://localhost:8000/docs
```

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado y disponibilidad de artefactos |
| `POST /predict` | Pronóstico por municipio/categoría/horizonte |
| `POST /simulate` | Simulación de escenarios "¿y si…?" (palancas de intervención/población) |
| `GET /anomalies` | Anomalías detectadas |
| `GET /monitoring` | Salud del modelo (frescura, deriva PSI, backtest 12m) |
| `POST /rag/chat` | Asistente ciudadano (RAG clásico o agente con herramientas) |
| `GET /brief/{cod}` | Informe ejecutivo municipal (IA generativa anclada) |

## Estructura

```
vigia/
├── config.py            # configuración 12-factor
├── datasets.py          # catálogo de fuentes SODA2 + capa Justicia (Fiscalía)
├── ingest/soda.py       # cliente SODA2 (paginación, reintentos, streaming keyset)
├── etl/                 # bronze · silver · gold · quality · load · divipola · poblacion · justicia
├── ml/                  # features · forecasting · anomaly · simulation · monitoring ·
│                        #   challenger · anomaly_validation · evaluate
├── rag/                 # providers · ingest · pipeline · agent · tools · brief · hybrid · documents
└── api/                 # FastAPI (main · schemas)
```

## Pruebas

```bash
pytest -q
```

## Proveedor de LLM

Configurable por `LLM_PROVIDER` (`ollama` | `anthropic` | `openai`) y `EMBED_PROVIDER`. Por defecto
usa **Ollama local** (cero costo, sin enviar datos a terceros). Ver `.env.example`.

> [!NOTE]
> El **agente** (`rag/agent.py`, que el LLM use herramientas y las encadene) solo se activa con 
> un proveedor que soporte uso de herramientas (*tool-use*: **Anthropic/OpenAI**); con 
> **Ollama local** —el camino por defecto— el asistente cae con elegancia al **RAG clásico** 
> (`rag/pipeline.py`), sin regresión pero **sin encadenado de herramientas**. Para la demo del agente, 
> usar `LLM_PROVIDER=anthropic` u `openai`. La única **red neuronal** del proyecto (`MLPRegressor`
> en `ml/challenger.py`) es un **arnés de evaluación**: no llega a producción —el modelo en producción es
> *gradient boosting* (`HistGradientBoostingRegressor`)—.
