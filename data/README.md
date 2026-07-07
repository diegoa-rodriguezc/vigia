# `data/` — Lago de datos (arquitectura medallion)

Esta carpeta es el **lago de datos** de VigIA. Los datos fluyen por tres capas
(`bronze → silver → gold`, ver [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#3-flujo-de-datos-pipeline))
y una cuarta carpeta (`kb_docs/`) guarda los documentos de la base de conocimiento del asistente.

| Carpeta | Contenido | ¿Versionada en git? |
|---|---|---|
| `bronze/` | **Crudo fiel** por fuente: un `<fuente>.parquet` + un `<fuente>.meta.json` de **linaje** (id SODA2, URL de origen, nº de filas, hash SHA-256 y fecha de ingesta) | No, se regenera con `vigia ingest` |
| `silver/` | El modelo **unificado** de eventos (`eventos.parquet`): las dos familias de esquema y los dos formatos de fecha de las fuentes, normalizados a un único esquema | No, se regenera con `vigia clean` |
| `gold/` | Los artefactos **servidos**: `serie_mensual`, `resumen_municipio`, `resumen_categoria`, `anomalias` y la capa Justicia (`justicia_anual`, `justicia_resumen`), en Parquet | No, se regenera con `vigia gold` / `vigia justicia` |
| `kb_docs/` | **Documentos no estructurados** (PDF/Word) que el RAG indexa y cita por página | **Sí** (ver abajo) |

## Cómo regenerar las capas no versionadas

Las tres capas del medallion son **artefactos regenerables** (por eso están en `.gitignore`, con un
`.gitkeep` que preserva la carpeta). El pipeline completo las reconstruye desde las fuentes abiertas:

```bash
make deploy            # despliegue completo (incluye el pipeline dentro de Docker)
make docker-pipeline   # solo el pipeline, si los servicios ya están arriba
```

Para rehacer **una sola fuente** sin re-descargar todo (p. ej. si una fuente cambió o falló):

```bash
make docker-reingest ONLY=homicidios          # una fuente
make docker-reingest ONLY="homicidios extorsion"  # varias
```

> [!NOTE]
> **Rutas dentro de Docker:** el contenedor `ml` fija `VIGIA_DATA_DIR=/app/data` (ver
> `docker-compose.yml`) y esta carpeta está montada como **volumen**, así que los datos sobreviven a la
> recreación del contenedor. El código **no** está montado: un cambio en `ml/vigia/` requiere
> `docker compose build ml`.

## `kb_docs/` — documentos del asistente

Los archivos de esta carpeta se indexan en la base de conocimiento del RAG con
`make docker-rag-index` (fragmentos con solape, citados **por página**). Para añadir un documento:
colóquelo aquí y ejecute ese comando.

El PDF incluido (*Política de Seguridad, Defensa y Convivencia Ciudadana 2022-2026*) es la **copia
íntegra** del documento oficial publicado por la Policía Nacional; su procedencia verificada está en
[docs/DATASETS.md](../docs/DATASETS.md#recursos-complementarios-fuera-de-soda2--procedencia-y-atribución).
Se versiona a propósito, para que el pilar de **datos no estructurados** sea reproducible en un clon.

## Referencias

- Diccionario de datos (campos, fuentes, esquemas): [docs/DATA_DICTIONARY.md](../docs/DATA_DICTIONARY.md)
- Inventario de fuentes con URLs: [docs/DATASETS.md](../docs/DATASETS.md)
- Calidad de la ejecución vigente (conteos, placeholders, rangos): [reports/silver_quality.json](../reports/silver_quality.json)
