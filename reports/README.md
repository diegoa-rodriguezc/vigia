# `reports/` — Cifras auditables del proyecto

Esta carpeta contiene los **reportes reproducibles** que generan el pipeline y los comandos de evaluación
del proyecto. A diferencia del lago de datos y los modelos (regenerables y no versionados),
**estos JSON sí se versionan a propósito**: son las cifras que cita la documentación
([README.md](../README.md), [docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md), [docs/IMPACTO.md](../docs/IMPACTO.md)) y permiten
**auditar el modelo y los datos sin ejecutar el pipeline**.

> **Licencia:** estos reportes son **obras derivadas** de los datos abiertos de origen (CC BY-SA 4.0) y
> se comparten bajo esa **misma licencia**, con atribución a las entidades publicadoras (ver la sección
> Licencia del [README](../README.md#-licencia)); el código que los genera es MIT.

| Archivo | Qué contiene | Se regenera con |
|---|---|---|
| `silver_quality.json` | Calidad de la capa silver: filas por fuente, rango de fechas, municipios/categorías únicos, `completitud_pct`, el **`placeholders_pct`** (% real de `NO REPORTADO` por campo) y la **`procedencia`** por fuente (conciliación crudo→silver + **fecha de ingesta** `ingerido_el`, linaje auditable desde el repo) | `vigia clean` (parte del pipeline) |
| `model_report.json` | El **backtest completo** del pronóstico: MAE/MASE/sMAPE del modelo frente a las dos líneas base (persistencia y estacional), a 1 paso y multipaso, desglose por tercil de volumen, cobertura de la banda (`pi_*`) e importancias de features | `vigia train` (parte del pipeline) |
| `justicia.json` | Cifras de la capa Justicia (Fiscalía): embudo de judicialización (por clase y **por etapa cruda** de la cadena penal), **tasa de judicialización nacional**, **tasa por título del Código Penal** (`tasa_por_delito`, ranking con umbral mínimo de volumen), **tasa por año del hecho** (`tasa_por_anio`, evidencia del efecto cohorte) y **`procedencia`** (conciliación bronze → gold con los descartes por causa) | `vigia justicia` (parte del pipeline) |
| `anomaly_validation.json` | Validación de las anomalías **reales**: recall@ventana contra el catálogo de eventos documentados y **corroboración interna** (fracción respaldada por otra categoría en el mismo municipio-mes); incluye el **corte del dato** validado | `vigia validate-anomalies` (parte del pipeline) |
| `model_health.json` | **Salud del modelo** (semáforo): frescura del dato (con desglose de **fuentes estancadas** por categoría), deriva vía PSI, **cobertura del denominador poblacional** y backtest extendido a 12 meses; alimenta la pestaña *Salud del modelo* del tablero | `vigia health` / `make docker-health` (**offline**, lento — no va en el pipeline) |
| `challenger.json` | Comparación **champion vs challenger**: el HGB de producción frente a un desafiante neuronal (MLP) bajo el mismo backtest; solo evalúa, no cambia el modelo en producción | `make docker-challenger` (offline, bajo demanda) |
| `blend_sweep.json` | **Análisis de sensibilidad del peso de la mezcla** modelo/persistencia (`_BLEND_W`): MAE/MASE/sMAPE a 1 paso y multipaso para cada peso de 1,0 a 0,3. Es la evidencia de por qué se fijó **0,7** —el mayor peso del modelo que gana a la persistencia tanto a 1 paso como en el horizonte completo— y con ese peso reproduce `model_report.json`; sustenta la Iteración 12 de la bitácora | `make docker-blend-sweep` (experimento puntual con `ml/scripts/blend_sweep.py`, **no** forma parte del pipeline; se relanza a mano si el modelo cambia de forma sustancial) |
| `rag_eval.json` | **Evaluación del asistente** (modo agente + proveedor gestionado) con preguntas de referencia derivadas de gold/reports: exactitud de cifras, **abstención correcta** ante lo fuera de alcance (el guardarraíl, medido), citación de fuentes y latencia | `make docker-rag-eval` (offline; requiere BD + proveedor LLM; admite `RAG_EVAL_ARGS`) |
| `rag_eval_ollama.json` | **Evaluación del asistente por el camino POR DEFECTO** (Ollama local + RAG clásico, sin API key): las mismas preguntas de referencia contra el despliegue que ve quien clona el proyecto tal cual. Registra la `temperatura` (0, medida: con 0,2 las respuestas variaban entre ejecuciones) y deja **declarados sus fallos consistentes** en el detalle (el total nacional de la Fiscalía y una pregunta fuera de alcance que el modelo de 1,7B responde igual) | `make docker-rag-eval-ollama` (offline, **muy lento en CPU** ~30 min; el índice debe estar construido con embeddings de Ollama — ver el comentario del Makefile) |

## Cómo leerlos

- Cada archivo es la **instantánea de la ejecución que lo generó** (los cuatro primeros se refrescan con
  `make docker-pipeline`; los cinco últimos se ejecutan a mano cuando se requieren).
- Las métricas del boosting pueden fluctuar **~1 % entre ejecuciones** por ruido numérico multi-hilo; las
  conclusiones cualitativas son estables (detalle en
  [docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md#3-ingeniería-del-modelo)).
- Si una cifra de la documentación no coincide exactamente con el JSON, **prevalece el JSON
  regenerado** — la documentación cita la ejecución de referencia.

## Recomendación operativa

Para comparación longitudinal (¿el modelo mejora o se degrada mes a mes?), archive cada ejecución con
marca temporal (p. ej. `reports/history/model_report_<trained_at>.json`) antes de sobreescribirla —
es la práctica sugerida en [docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md#63-versionado-de-modelos-y-trazabilidad).
