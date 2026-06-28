-- Inicialización de la base de datos de VigIA.
-- La imagen pgvector/pgvector ya trae la extensión; aquí la habilitamos.
CREATE EXTENSION IF NOT EXISTS vector;

-- Las tablas de datos (resumen_municipio, serie_mensual, anomalias) y la tabla
-- kb_chunks del RAG se crean desde el pipeline Python
-- (vigia load-db / vigia rag-index), para mantener el esquema junto a su lógica.
