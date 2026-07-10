# VigIA - atajos del ciclo de vida del proyecto
.DEFAULT_GOAL := help
.PHONY: help up down logs pipeline ml-install ml-api ml-test \
        ingest clean gold justicia train validate-anomalies load-db rag-index health \
        backend-run backend-test frontend-dev fmt \
        docker-pipeline docker-health docker-rag-index docker-reingest ollama-pull deploy deploy-gpu \
        kb-docs docker-challenger docker-rag-eval docker-rag-eval-ollama docker-blend-sweep

# Comando base de Compose. 
COMPOSE ?= docker compose

# Carga el .env si existe; si no, las variables usan los defaults de abajo.
ifneq (,$(wildcard .env))
include .env
endif

# Defaults a nivel de make (`?=` no reemplaza lo que ya vino del .env).
# DEBEN coincidir con los de .env.example: si divergen, `make ollama-pull` sin .env
# descargaría modelos distintos de los que el servicio ml espera.
OLLAMA_LLM_MODEL ?= qwen3:1.7b
OLLAMA_EMBED_MODEL ?= qwen3-embedding:0.6b
export OLLAMA_LLM_MODEL OLLAMA_EMBED_MODEL

help: ## Muestra la ayuda
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# == Orquestación Docker ==
# --wait bloquea hasta que los healthchecks pasen, respetando el orden de `depends_on: service_healthy`
up: ## Levanta todos los servicios (db, ollama, ml, backend, frontend)
	$(COMPOSE) up -d --build --wait

down: ## Detiene y elimina los contenedores
	$(COMPOSE) down

logs: ## Muestra logs en vivo
	$(COMPOSE) logs -f

# == Despliegue (todo dentro de Docker) ==
deploy: up ollama-pull kb-docs docker-pipeline ## Despliegue completo: levanta servicios (db, ollama, ml, backend, frontend) + modelos + pipeline con datos

# Superpone docker-compose.gpu.yml (reserva de GPU para Ollama). Requiere driver
# NVIDIA + NVIDIA Container Toolkit (Linux) o Docker Desktop+WSL2 (Windows). 
deploy-gpu: ## Despliegue con aceleración GPU (NVIDIA): igual que `deploy` + override GPU
	$(MAKE) deploy COMPOSE="docker compose -f docker-compose.yml -f docker-compose.gpu.yml"

ollama-pull: ## Descarga los modelos LLM/embeddings dentro del contenedor de Ollama
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_LLM_MODEL)
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_EMBED_MODEL)

docker-pipeline: ## Ejecuta el pipeline completo DENTRO del contenedor ml (hostnames de la red Docker)
	$(COMPOSE) exec ml python -m vigia pipeline

# Monitoreo offline (CRISP-ML(Q) fase 6): NO va en el pipeline ni en `deploy` a propósito,
# porque el backtest extendido a 12 meses recalcula features sobre todo el panel y tarda
# minutos. Se ejecuta a mano cuando se requiere actualizar la pestaña "Salud del modelo". 
docker-health: ## Regenera la salud del modelo (reports/model_health.json) DENTRO del contenedor ml. Proceso Lento.
	$(COMPOSE) exec ml python -m vigia health

# Reportes de evaluación BAJO DEMANDA (no van en el pipeline ni en `deploy`): se ejecutan a mano
# cuando se requieren. Todos corren DENTRO del contenedor ml (necesitan gold/BD; rag-eval además un
# proveedor LLM activo). Ver reports/README.md.
docker-challenger: ## Evalúa el retador neuronal vs el HGB de producción (reports/challenger.json). Lento.
	$(COMPOSE) exec ml python -m vigia challenger

# RAG_EVAL_ARGS permite pasar opciones del CLI (p. ej. RAG_EVAL_ARGS="--modo clasico --out otro.json").
docker-rag-eval: ## Evalúa el asistente con preguntas de referencia (reports/rag_eval.json). Requiere proveedor LLM.
	$(COMPOSE) exec ml python -m vigia rag-eval $(RAG_EVAL_ARGS)

# Fuerza el camino POR DEFECTO (Ollama local + RAG clásico) aunque el .env apunte a un proveedor
# gestionado. Advertencia: el índice kb_chunks debe estar construido con el MISMO proveedor de
# embeddings; si el .env usa otro, reconstruirlo antes y después:
#   docker compose exec -e EMBED_PROVIDER=ollama ml python -m vigia rag-index   (antes)
#   make docker-rag-index                                                       (después, restaura)
docker-rag-eval-ollama: ## Evalúa el camino por defecto (Ollama + RAG clásico) → reports/rag_eval_ollama.json. Muy lento en CPU (~30 min).
	$(COMPOSE) exec -T -e LLM_PROVIDER=ollama -e EMBED_PROVIDER=ollama ml python -m vigia rag-eval --modo clasico --out rag_eval_ollama.json

# El análisis de sensibilidad NO es un subcomando `vigia` sino un script; como el código no está
# montado en el contenedor, se pasa por la entrada estándar (-T), igual que kb-docs.
docker-blend-sweep: ## Análisis de sensibilidad del peso de la mezcla modelo/persistencia (reports/blend_sweep.json). Lento (~10 min).
	$(COMPOSE) exec -T ml python - < ml/scripts/blend_sweep.py

# Reconstruye SOLO el índice del RAG (kb_chunks) DENTRO del contenedor ml, sin rehacer el pipeline.
# Útil tras añadir documentos a data/kb_docs/ o cambiar el embedder.
docker-rag-index: ## Reconstruye el índice del RAG (kb_chunks) DENTRO del contenedor ml
	$(COMPOSE) exec ml python -m vigia rag-index

# Verifica la INTEGRIDAD (SHA-256 y tamaño) del PDF de la Política de Seguridad versionado
# en data/kb_docs/; si faltara o no coincidiera, lo descarga del sitio oficial. Si el
# archivo ya existe y su hash coincide, no vuelve a descargarlo. El código no está montado
# en el contenedor → el script se pasa por la entrada estándar (-T).
kb-docs: ## Verifica (SHA-256) los documentos de la KB del RAG y los re-obtiene si faltan
	$(COMPOSE) exec -T ml python - < ml/scripts/fetch_kb_docs.py

# Re-ingesta selectiva + reconstrucción de lo derivado, GENÉRICO para cualquier fuente.
#   make docker-reingest ONLY=poblacion               # una fuente
#   make docker-reingest ONLY="homicidios extorsion"  # varias (un --only por dataset)
#   make docker-reingest                              # todas
# Reconstruye la imagen ml (por si cambió código/deps, p. ej. una nueva dependencia) y la
# recrea ANTES de los exec (recrear el contenedor mata cualquier exec en curso). 
docker-reingest: ## Re-ingesta dataset(s) y reconstruye silver->gold->train->load-db. Uso: make docker-reingest ONLY=poblacion
	$(COMPOSE) build ml
	$(COMPOSE) up -d ml
	$(COMPOSE) exec ml python -m vigia ingest $(foreach d,$(ONLY),--only $(d))
	$(COMPOSE) exec ml python -m vigia clean
	$(COMPOSE) exec ml python -m vigia gold
	$(COMPOSE) exec ml python -m vigia train
	$(COMPOSE) exec ml python -m vigia load-db
	-$(COMPOSE) exec ml python -m vigia rag-index

# == Pipeline de datos / ML (Python) ==
ml-install: ## Instala el paquete Python en modo editable
	cd ml && pip install -e ".[dev]"

# Mismo orden que `pipeline()` en ml/vigia/cli.py (incluye la capa Justicia y la validación de anomalías)
pipeline: ingest clean gold justicia train validate-anomalies load-db rag-index ## Ejecuta el pipeline completo end-to-end

ingest: ## Descarga datos abiertos (SODA2) -> bronze
	cd ml && python -m vigia ingest

clean: ## Limpieza y unificación -> silver
	cd ml && python -m vigia clean

gold: ## Agregación y features -> gold
	cd ml && python -m vigia gold

justicia: ## Construye la capa Justicia (Fiscalía) -> gold + reports/justicia.json
	cd ml && python -m vigia justicia

train: ## Entrena forecasting + anomalías -> models/
	cd ml && python -m vigia train

validate-anomalies: ## Valida las anomalías reales (catálogo de eventos + corroboración) -> reports/
	cd ml && python -m vigia validate-anomalies

load-db: ## Carga la capa gold a PostgreSQL
	cd ml && python -m vigia load-db

rag-index: ## Construye el índice del RAG en pgvector
	cd ml && python -m vigia rag-index

health: ## Regenera reports/model_health.json (frescura, deriva PSI, backtest 12m). Monitoreo offline (lento).
	cd ml && python -m vigia health

ml-api: ## Levanta el servicio FastAPI en local
	cd ml && uvicorn vigia.api.main:app --reload --port 8000

ml-test: ## Ejecuta las pruebas del paquete Python
	cd ml && pytest -q

# == Backend (Go) ==
backend-run: ## Ejecuta la API Go en local
	cd backend && go run ./cmd/api

backend-test: ## Ejecuta las pruebas de Go
	cd backend && go test ./...

# == Frontend (React) ==
frontend-dev: ## Levanta el frontend en modo desarrollo
	cd frontend && npm install && npm run dev

fmt: ## Formatea Python y Go
	cd ml && ruff format . && ruff check --fix .
	cd backend && go fmt ./...
