"""Ingesta de documentos NO estructurados (PDF/Word) a la base de conocimiento del RAG.

Extrae el texto de los documentos colocados en `settings.rag_docs_dir`, lo parte en
fragmentos solapados y los emite como *cards* con el mismo formato que las data cards de
gold, de modo que se indexan en `kb_chunks` y se recuperan/citan por el pipeline existente
sin cambios. Así el asistente puede responder también sobre el marco normativo y de política
pública, no solo sobre las cifras.
"""

from __future__ import annotations

from pathlib import Path

from vigia.config import settings
from vigia.logging import get_logger

log = get_logger(__name__)


def chunk_text(text: str, size: int = 800, overlap: int = 150) -> list[str]:
    """Parte un texto en fragmentos de ~`size` caracteres con `overlap` de solapamiento.

    Normaliza espacios/saltos de línea y solapa los fragmentos para no perder frases que
    queden a caballo entre dos cortes (clave para la recuperación semántica). Función pura
    (sin E/S) para poder probarla sin archivos.
    """
    norm = " ".join(text.split())
    if not norm:
        return []
    if len(norm) <= size:
        return [norm]
    step = max(1, size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(norm):
        fragment = norm[start : start + size].strip()
        if fragment:
            chunks.append(fragment)
        if start + size >= len(norm):
            break
        start += step
    return chunks


def _extract_pdf(path: Path) -> list[tuple[int | None, str]]:
    """Devuelve [(nº de página, texto)] de un PDF con capa de texto (no escaneado)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    out: list[tuple[int | None, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 — una página ilegible no debe tumbar la ingesta
            text = ""
        if text.strip():
            out.append((i, text))
    return out


def _extract_docx(path: Path) -> list[tuple[int | None, str]]:
    """Devuelve [(None, texto)] de un .docx (Word no tiene paginación fiable)."""
    import docx

    document = docx.Document(str(path))
    full = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    return [(None, full)] if full.strip() else []


_LOADERS = {".pdf": _extract_pdf, ".docx": _extract_docx}


def document_cards(
    docs_dir: Path | None = None, chunk_size: int = 800, overlap: int = 150
) -> list[dict]:
    """Lee los documentos de `docs_dir` y los convierte en cards chunkeadas para el índice.

    Cada fragmento lleva metadatos de cita: `tipo='documento'`, `fuente` (nombre del archivo)
    y, para PDF, la `pagina`. Formatos soportados: .pdf y .docx. Si la carpeta no existe o
    está vacía, devuelve [] (la KB sigue funcionando solo con las data cards de gold).
    """
    docs_dir = docs_dir or settings.rag_docs_dir
    if not docs_dir.exists():
        return []

    cards: list[dict] = []
    for path in sorted(docs_dir.glob("**/*")):
        loader = _LOADERS.get(path.suffix.lower())
        if loader is None:
            continue
        try:
            pages = loader(path)
        except Exception as exc:  # noqa: BLE001 — un documento ilegible no detiene el resto
            log.warning("No se pudo leer el documento %s: %s", path.name, exc)
            continue

        count = 0
        for pagina, text in pages:
            for fragment in chunk_text(text, chunk_size, overlap):
                metadata = {"tipo": "documento", "fuente": path.stem}
                if pagina is not None:
                    metadata["pagina"] = pagina
                cards.append({"content": fragment, "metadata": metadata})
                count += 1
        log.info("Documento '%s': %d fragmentos indexables", path.name, count)

    return cards
