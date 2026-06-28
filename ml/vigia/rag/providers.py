"""Abstracción de proveedores de LLM y embeddings.

Permite cambiar entre Ollama (local, por defecto), Anthropic (Claude) y OpenAI
mediante configuración, sin tocar el resto del RAG. Diseño con interfaz común
(`EmbeddingProvider`, `LLMProvider`) y *factory* por variable de entorno.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)


# ───────────────────────── Embeddings ─────────────────────────
class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbeddings(EmbeddingProvider):
    def __init__(self) -> None:
        self.url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_embed_model
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        # La dimensión la DICTA el modelo configurado (all-minilm=384, nomic-embed-text=768,
        # etc.). Al cambiar OLLAMA_EMBED_MODEL en el .env no descuadra el `vector(dim)` 
        # de la tabla kb_chunks
        if self._dim is None:
            self._dim = len(self.embed(["dim"])[0])
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        with httpx.Client(timeout=120) as client:
            for t in texts:
                r = client.post(
                    f"{self.url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": t,
                        # keep_alive mantiene el embedder en memoria entre consultas (evita
                        # recargas frías); las opciones acotan la latencia de generación. Mismo
                        # valor que el LLM (OLLAMA_KEEP_ALIVE) para que ambos sigan residentes.
                        "keep_alive": settings.ollama_keep_alive,
                        # num_ctx fija el contexto/batch del embedder. Sin esto Ollama carga el
                        # modelo con un contexto pequeño (256) y un fragmento largo (chunk_text
                        # corta por caracteres, no por tokens: ~800 car. ≈ 200-290 tokens) supera
                        # el batch y devuelve 500. El default (2048) cubre cualquier chunk con
                        # holgura (Ollama lo acota al máximo del modelo); COMPARTE OLLAMA_NUM_CTX
                        # con OllamaLLM (deben coincidir).
                        "options": {"num_ctx": settings.ollama_num_ctx},
                    },
                )
                r.raise_for_status()
                out.append(r.json()["embedding"])
        return out


class LocalEmbeddings(EmbeddingProvider):
    """sentence-transformers multilingüe (requiere extra `rag-local`)."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # import perezoso

        self.model = SentenceTransformer(settings.local_embed_model)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()


class OpenAIEmbeddings(EmbeddingProvider):
    dim = 1536  # text-embedding-3-small

    def __init__(self) -> None:
        from openai import OpenAI  # import perezoso

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embed_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


# ───────────────────────── LLM ─────────────────────────
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, prompt: str) -> str: ...


class OllamaLLM(LLMProvider):
    def __init__(self) -> None:
        self.url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_llm_model

    def generate(self, system: str, prompt: str) -> str:
        # 230s alinea este cliente con el presupuesto documentado (~240s en axios, WriteTimeout
        # de Go y middleware.Timeout)
        with httpx.Client(timeout=230) as client:
            r = client.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    # keep_alive mantiene el modelo en memoria entre consultas (evita
                    # recargas frías); las opciones acotan la latencia de generación.
                    "keep_alive": settings.ollama_keep_alive,
                    # think: con modelos de razonamiento (qwen3, deepseek-r1…) el LLM gastaría todo
                    # el presupuesto `num_predict` PENSANDO y cortaría (done_reason="length") antes
                    # de emitir respuesta → `content` vacío (texto en blanco, pero con fuentes). Por
                    # defecto apagado para volcar el presupuesto en la respuesta; en modelos sin
                    # razonamiento es inocuo (ya es su estado).
                    "think": settings.ollama_think,
                    # Afinables al hardware vía .env (defaults históricos: 0.2 / 220 / 2048).
                    "options": {
                        "temperature": settings.ollama_temperature,
                        "num_predict": settings.ollama_num_predict,  # tope de tokens (acota CPU)
                        "num_ctx": settings.ollama_num_ctx,
                    },
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            r.raise_for_status()
            msg = r.json()["message"]
            # Fallback defensivo: si `think` quedó activo y se truncó dentro del razonamiento,
            # `content` viene vacío pero `thinking` trae texto → al menos no devolver el blanco.
            return msg.get("content") or msg.get("thinking") or ""


class AnthropicLLM(LLMProvider):
    def __init__(self) -> None:
        import anthropic  # import perezoso

        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def generate(self, system: str, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")


class OpenAILLM(LLMProvider):
    def __init__(self) -> None:
        from openai import OpenAI  # import perezoso

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def generate(self, system: str, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""


# ───────────────────────── Factories ─────────────────────────
def get_embedder() -> EmbeddingProvider:
    provider = settings.embed_provider.lower()
    log.info("Embeddings: proveedor=%s", provider)
    if provider == "ollama":
        return OllamaEmbeddings()
    if provider == "local":
        return LocalEmbeddings()
    if provider == "openai":
        return OpenAIEmbeddings()
    raise ValueError(f"EMBED_PROVIDER desconocido: {provider}")


def get_llm() -> LLMProvider:
    provider = settings.llm_provider.lower()
    log.info("LLM: proveedor=%s", provider)
    if provider == "ollama":
        return OllamaLLM()
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    raise ValueError(f"LLM_PROVIDER desconocido: {provider}")
