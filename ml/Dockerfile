# ── Servicio ML de VigIA (ETL + modelos + RAG + API FastAPI) ──
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias del sistema mínimas para pandas/pyarrow/psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependencias primero (mejor caché de capas).
# README.md es necesario: pyproject.toml lo declara como `readme`.
COPY pyproject.toml README.md ./
COPY vigia ./vigia
RUN pip install --upgrade pip && pip install -e ".[openai,anthropic]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "vigia.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
