# `reports/` — Cifras auditables del proyecto

Esta carpeta contiene los **reportes reproducibles** que el pipeline y los comandos de evaluación
emiten en cada ejecución. A diferencia del lago de datos y los modelos (regenerables y no versionados),
**estos JSON sí se versionan a propósito**: son las cifras que cita la documentación
([README.md](../README.md), [docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md), [docs/IMPACTO.md](../docs/IMPACTO.md)) y permiten
**auditar el modelo y los datos sin ejecutar el pipeline**.

| Archivo | Qué contiene | Se regenera con |
|---|---|---|
| `silver_quality.json` | Calidad de la capa silver: filas por fuente, rango de fechas, municipios/categorías únicos, `completitud_pct` y el **`placeholders_pct`** (% real de `NO REPORTADO` por campo) | `vigia clean` (parte del pipeline) |
| `model_report.json` | El **backtest completo** del pronóstico: MAE/MASE/sMAPE del modelo frente a las dos líneas base (persistencia y estacional), a 1 paso y multipaso, desglose por tercil de volumen, cobertura de la banda (`pi_*`) e importancias de features | `vigia train` (parte del pipeline) |
| `justicia.json` | Cifras de la capa Justicia (Fiscalía): embudo de judicialización por etapa y **tasa de judicialización nacional** | `vigia justicia` (parte del pipeline) |
| `anomaly_validation.json` | Validación de las anomalías **reales**: recall@ventana contra el catálogo de eventos documentados y **corroboración interna** (fracción respaldada por otra categoría en el mismo municipio-mes) | `vigia validate-anomalies` (parte del pipeline) |
| `model_health.json` | **Salud del modelo** (semáforo): frescura del dato, deriva vía PSI y backtest extendido a 12 meses; alimenta la pestaña *Salud del modelo* del tablero | `vigia health` / `make docker-health` (**offline**, lento — no va en el pipeline) |
| `challenger.json` | Comparación **champion vs challenger**: el HGB de producción frente a un desafiante neuronal (MLP) bajo el mismo backtest; solo evalúa, no cambia el modelo servido | `vigia challenger` (offline, bajo demanda) |

## Cómo leerlos

- Cada archivo es la **instantánea de la ejecución que lo generó** (los cuatro primeros se refrescan con
  `make docker-pipeline`; los dos últimos, a mano cuando se requieren).
- Las métricas del boosting pueden fluctuar **~1 % entre ejecuciones** por ruido numérico multi-hilo; las
  conclusiones cualitativas son estables (detalle en
  [docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md#3-ingeniería-del-modelo)).
- Si una cifra de la documentación no coincide exactamente con el JSON, **prevalece el JSON
  regenerado** — la documentación cita la ejecución de referencia.

## Recomendación operativa

Para comparación longitudinal (¿el modelo mejora o se degrada mes a mes?), archive cada ejecución con
marca temporal (p. ej. `reports/history/model_report_<trained_at>.json`) antes de sobreescribirla —
es la práctica sugerida en [docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md#63-versionado-de-modelos-y-trazabilidad).
