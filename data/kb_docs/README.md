# `kb_docs/` — documentos de la base de conocimiento del asistente

Los PDF/Word de esta carpeta se indexan en el RAG (fragmentos con solape, citados **por página**)
con `make docker-rag-index`. Para añadir un documento: colóquelo aquí y ejecute ese comando.

## El documento incluido

*Política de Seguridad, Defensa y Convivencia Ciudadana 2022-2026* (Ministerio de Defensa
Nacional, publicada por la Policía Nacional): **copia íntegra y sin modificaciones** del
[documento oficial](https://www.policia.gov.co/sites/default/files/2024-12/Pol%C3%ADtica%20de%20Seguridad%20Defensa%20y%20Convivencia%20Ciudadna.pdf)
*[sic: la errata «Ciudadna» de la URL es del sitio de origen]*, versionada en el repositorio con
cita de su fuente — al amparo de la reproducción de textos oficiales (art. 41, Ley 23 de 1982) —
para que el pilar de **datos no estructurados** sea reproducible en un clon.

**Integridad verificable:** `make kb-docs` comprueba el SHA-256
(`5b169a5a87ec7f9de57d7879ee4fa22fc83e9f288e1e0a903939a666b9f6af1a`, 47.785.152 bytes,
verificado contra el original en línea el 2026-07-08) y, si el archivo faltara o no coincidiera,
lo re-obtiene del sitio oficial (ver [`ml/scripts/fetch_kb_docs.py`](../../ml/scripts/fetch_kb_docs.py)).

Si la carpeta quedara vacía, el índice del RAG **degrada con elegancia**: el asistente sigue
funcionando solo con las *data cards* de las cifras (sin el marco de política pública).
