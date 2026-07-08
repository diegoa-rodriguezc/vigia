# Documentación de VigIA

Contenido de la carpeta `docs/`.

## Índice de documentos

| Orden | Documento | Qué contiene | Pensado para |
|:---:|---|---|---|
| 1 | [IMPACTO.md](IMPACTO.md) | Problema cuantificado, **teoría de cambio** (dato → decisión → acción), caso de uso, valor territorial y escalabilidad. | Jurado · entidades |
| 2 | [ADOPCION.md](ADOPCION.md) | **Ruta de adopción y plan piloto** (plan 30/60/90 días), qué aporta cada parte, por qué es de bajo riesgo. | Entidades públicas |
| 3 | [CRISP-ML-Q.md](CRISP-ML-Q.md) | **Metodología CRISP-ML(Q)**: las 6 fases, evaluación del modelo, **bitácora de iteración** (hallazgos reales) y ética/uso responsable. | Jurado · desarrollo |
| 4 | [ARCHITECTURE.md](ARCHITECTURE.md) | **Arquitectura**: principios, vista de componentes, flujo del pipeline, contratos de API y **decisiones (ADR)**. | Desarrollo |
| 5 | [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | **Diccionario de datos**: fuentes, esquemas crudos y unificado, capa Justicia, población DANE, tablas de PostgreSQL. | Desarrollo · datos |
| 6 | [DATASETS.md](DATASETS.md) | **Inventario de fuentes** consultadas, validación contra la **Hoja de Ruta Nacional** y descartes justificados. | Datos · trazabilidad |
| 7 | [HOJA_RUTA_SECTORIAL.md](HOJA_RUTA_SECTORIAL.md) | Alineación con las **Hojas de Ruta SECTORIALES** (Defensa y Justicia, con el PDF oficial de Justicia como evidencia) e índice de las 25 hojas. | Jurado · trazabilidad |
| — | [CONCURSO.md](CONCURSO.md) | Copia de los **términos de referencia** del concurso (contexto, reglas, criterios). *No es documentación del proyecto.* | Referencia |

---

## Diagramas

Fuentes editables en [`diagrams/`](diagrams/) (formato [Excalidraw](https://excalidraw.com)):

| Diagrama | Descripción |
|---|---|
| [Pipeline de datos](diagrams/pipeline-datos.png) | Flujo `ingest → clean → gold → justicia → train → load-db → rag-index` (medallion + capa Justicia paralela). |
| [Arquitectura de componentes](diagrams/arquitectura.png) | Las 3 capas (React · Go · Python/FastAPI) sobre PostgreSQL + pgvector, con Redis y Ollama. |

Se muestran en contexto dentro de [ARCHITECTURE.md](ARCHITECTURE.md) y el [README principal](../README.md).

---

## Otros recursos

- [`screenshots/`](screenshots/) — capturas de las 8 vistas del tablero (usadas en el README principal).
- [`../notebooks/`](../notebooks/README.md) — los tres notebooks del proceso (exploración de fuentes,
  limpieza silver y modelo) con su índice y guía de re-ejecución.
- [`img/`](img/) — imágenes de los términos del concurso (criterios, cronograma).
- [`../reports/`](../reports/) — **métricas reproducibles** en JSON que el pipeline regenera en cada ejecución/despliegue
  (`model_report.json`, `silver_quality.json`, `justicia.json`, `model_health.json`, `challenger.json`,
  `anomaly_validation.json`). Son las **cifras** que citan estos documentos.

