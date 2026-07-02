# VigIA - atajos del ciclo de vida del proyecto
.DEFAULT_GOAL := help
.PHONY: help up down logs pipeline ml-install ml-api ml-test \
        ingest clean gold train load-db rag-index health backend-run backend-test frontend-dev fmt \
        docker-pipeline docker-health docker-rag-index docker-reingest ollama-pull deploy deploy-gpu

# Comando base de Compose. 
COMPOSE ?= docker compose

# Carga el .env si existe; si no, las variables usan los defaults de abajo.
ifneq (,$(wildcard .env))
include .env
endif

# Defaults a nivel de make (`?=` no pisa lo que ya vino del .env). 
OLLAMA_LLM_MODEL ?= llama3.2:1b
OLLAMA_EMBED_MODEL ?= nomic-embed-text
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
deploy: up ollama-pull docker-pipeline ## Despliegue completo: levanta servicios (db, ollama, ml, backend, frontend) + modelos + pipeline con datos

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

# Reconstruye SOLO el índice del RAG (kb_chunks) DENTRO del contenedor ml, sin rehacer el pipeline.
# Útil tras añadir documentos a data/kb_docs/ o cambiar el embedder.
docker-rag-index: ## Reconstruye el índice del RAG (kb_chunks) DENTRO del contenedor ml
	$(COMPOSE) exec ml python -m vigia rag-index

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

pipeline: ingest clean gold train load-db rag-index ## Ejecuta el pipeline completo end-to-end

ingest: ## Descarga datos abiertos (SODA2) -> bronze
	cd ml && python -m vigia ingest

clean: ## Limpieza y unificación -> silver
	cd ml && python -m vigia clean

gold: ## Agregación y features -> gold
	cd ml && python -m vigia gold

train: ## Entrena forecasting + anomalías -> models/
	cd ml && python -m vigia train

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
