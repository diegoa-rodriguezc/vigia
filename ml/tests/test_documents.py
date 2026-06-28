"""Pruebas del chunking de documentos no estructurados para el RAG (sin E/S)."""

from vigia.rag.documents import chunk_text


def test_chunk_vacio_y_corto():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []
    assert chunk_text("hola mundo") == ["hola mundo"]  # cabe en un solo fragmento


def test_chunk_normaliza_espacios():
    assert chunk_text("hola   \n\n  mundo\t y  más") == ["hola mundo y más"]


def test_chunk_largo_con_solape():
    texto = "palabra " * 400  # ~3200 caracteres
    chunks = chunk_text(texto, size=800, overlap=150)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    # Solape: el final de un fragmento reaparece al inicio del siguiente (no se pierde texto).
    assert chunks[0][-50:] in (chunks[0] + chunks[1])


def test_chunk_cubre_todo_el_texto():
    texto = "".join(f"frase{i}. " for i in range(300))
    chunks = chunk_text(texto, size=500, overlap=100)
    # El último fragmento llega al final del texto normalizado.
    norm = " ".join(texto.split())
    assert norm.endswith(chunks[-1][-20:])
