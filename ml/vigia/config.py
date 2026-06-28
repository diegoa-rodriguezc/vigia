"""Configuración central (12-factor) basada en variables de entorno.

Todas las rutas se resuelven respecto a la raíz del repositorio para que el
pipeline funcione igual desde la CLI local, los notebooks y los contenedores.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repo: .../vigia (dos niveles por encima de este archivo: ml/vigia/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuración de la aplicación leída de variables de entorno y/o .env."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Rutas del lago de datos (medallion) ──
    # Configurables por entorno: en Docker el paquete vive en /app/vigia (REPO_ROOT
    # resolvería a `/`), por lo que se fijan explícitamente al volumen montado.
    data_dir: Path = Field(default=REPO_ROOT / "data", alias="VIGIA_DATA_DIR")
    models_dir: Path = Field(default=REPO_ROOT / "models", alias="VIGIA_MODELS_DIR")
    reports_dir: Path = Field(default=REPO_ROOT / "reports", alias="VIGIA_REPORTS_DIR")
    # Catálogo de eventos documentados para validar las anomalías (recall@ventana). Es contenido
    # curado y versionado (no un artefacto regenerado); en Docker `docs/` se monta read-only en
    # /app/docs (ver docker-compose.yml). Si el archivo no existe, la validación degrada con
    # elegancia a solo corroboración interna.
    events_catalog: Path = Field(
        default=REPO_ROOT / "docs" / "eventos_documentados.csv", alias="VIGIA_EVENTS_CATALOG"
    )

    # ── Ingesta SODA2 ──
    soda_app_token: str | None = Field(default=None, alias="SODA_APP_TOKEN")
    soda_max_rows: int | None = Field(default=None, alias="SODA_MAX_ROWS")

    # ── Base de datos ──
    database_url: str = Field(
        default="postgres://vigia:vigia_dev_password@localhost:5432/vigia?sslmode=disable",
        alias="DATABASE_URL",
    )

    # ── Proveedor LLM / embeddings para el RAG ──
    llm_provider: str = Field(default="ollama", alias="LLM_PROVIDER")
    embed_provider: str = Field(default="ollama", alias="EMBED_PROVIDER")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_llm_model: str = Field(default="llama3.2:1b", alias="OLLAMA_LLM_MODEL")
    ollama_embed_model: str = Field(default="nomic-embed-text", alias="OLLAMA_EMBED_MODEL")
    # Razonamiento ("thinking") de los modelos qwen3/deepseek-r1 y similares. Por defecto APAGADO:
    # en CPU el presupuesto de `num_predict` se agotaría dentro del bloque de razonamiento y la
    # respuesta saldría vacía (done_reason="length"). Solo activar con un modelo+hardware que lo tolere.
    ollama_think: bool = Field(default=False, alias="OLLAMA_THINK")
    # ── Afinado del runtime Ollama al hardware (LLM + embeddings) ──
    # Quemarlos obligaba a reconstruir la imagen para tunear; como env se ajustan recreando `ml`.
    # Defaults = valores históricos (cero cambio de comportamiento). `num_ctx` y `keep_alive` los
    # COMPARTEN el LLM y el embedder (deben coincidir: ver providers.py).
    ollama_temperature: float = Field(default=0.2, alias="OLLAMA_TEMPERATURE")
    # Tope de tokens generados: en CPU acota la latencia. OJO: subirlo puede reventar el muro de
    # timeouts (~240s) y, con modelos "thinking", agotarse pensando (ver ollama_think).
    ollama_num_predict: int = Field(default=220, alias="OLLAMA_NUM_PREDICT")
    # Ventana de contexto: más RAM. El embedder lo usa como batch (evita 500 en chunks largos).
    ollama_num_ctx: int = Field(default=2048, alias="OLLAMA_NUM_CTX")
    # Tiempo que Ollama mantiene el modelo residente entre consultas (evita recargas frías /
    # thrashing). Lo envían LLM y embedder por request (anula el default del servidor en compose).
    ollama_keep_alive: str = Field(default="30m", alias="OLLAMA_KEEP_ALIVE")
    local_embed_model: str = Field(
        default="intfloat/multilingual-e5-base", alias="LOCAL_EMBED_MODEL"
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-haiku-4-5-20251001", alias="ANTHROPIC_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_embed_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBED_MODEL")

    # Umbral de similitud mínima para que un fragmento recuperado se considere relevante en el RAG
    # (anti-alucinación). Es la perilla de CALIBRACIÓN del guardarraíl: subirlo rehúsa más (más
    # estricto, menos riesgo de inventar); bajarlo responde más. Configurable sin tocar el código.
    rag_min_score: float = Field(default=0.25, alias="RAG_MIN_SCORE")

    # Nº de fragmentos recuperados de kb_chunks por consulta. Más k = más cobertura pero prompt más
    # largo → LLM más lento en CPU (y más ruido que el guardarraíl de MIN_SCORE debe filtrar).
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")

    # ── Reproducibilidad ──
    seed: int = Field(default=77, alias="SEED")

    @field_validator("soda_max_rows", "soda_app_token", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        """Trata cadenas vacías (.env sin valor) como None en campos opcionales."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    # ── Carpetas de la arquitectura medallion ──
    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"

    @property
    def rag_docs_dir(self) -> Path:
        """Documentos no estructurados (PDF/Word/Markdown) para la base de conocimiento del RAG.

        Vive bajo `data/` (montado en el contenedor) para que `rag-index` los vea dentro de
        Docker. Coloca aquí PDFs/Word de política pública y se indexarán junto a las data cards.
        """
        return self.data_dir / "kb_docs"

    def ensure_dirs(self) -> None:
        """Crea las carpetas de salida si no existen."""
        for d in (
            self.bronze_dir,
            self.silver_dir,
            self.gold_dir,
            self.models_dir,
            self.reports_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
