# `models/` — Artefactos de modelo entrenados

Esta carpeta guarda los modelos **serializados** que utiliza la API de ML para responder. No se versionan en git
(son regenerables y pesados).

| Artefacto | Qué es |
|---|---|
| `forecaster.joblib` | El modelo de pronóstico: un `HistGradientBoostingRegressor` **global** (una sola instancia aprende de todas las series municipio × categoría) junto con su **metadata de entrenamiento** autoidentificable: `trained_at`, `seed`, `feature_cols`, métricas del backtest e importancias de features |
| `forecaster.meta.json` | **Registro de origen del modelo**, escrito junto al joblib en cada `vigia train`: anota qué versiones de `scikit-learn` y `numpy` lo crearon y cuándo (`trained_at`). Si la carga falla por incompatibilidad, el error nombra **quién escribió el modelo y con qué versiones** (no solo la del runtime) — diagnóstico en una línea |

Las **métricas auditables** de la ejecución que produjo el artefacto no viven aquí sino en
[reports/model_report.json](../reports/model_report.json), regenerado en cada entrenamiento.

## Cómo regenerar

```bash
make docker-pipeline    # pipeline completo dentro de Docker (incluye vigia train)
# o solo el entrenamiento, en local:
cd ml && python -m vigia train
```

Reproducibilidad: semilla global `SEED=77`. Las métricas pueden fluctuar **~1 % entre ejecuciones** (el
*early stopping* del boosting es sensible a las reducciones de punto flotante multi-hilo); las
conclusiones cualitativas son estables — detalle en
[docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md#3-ingeniería-del-modelo).

## ⚠️ El artefacto NO es portable entre versiones de scikit-learn

`scikit-learn` está fijado por versión menor (`>=1.9,<1.10` en `ml/pyproject.toml`) **a propósito**: un
`forecaster.joblib` serializado con una versión no se puede cargar con otra (cambian rutas internas y
`joblib.load` falla con errores como `ModuleNotFoundError: No module named '_loss'`).

- **Síntoma:** la API responde `503` con el mensaje accionable de reentrenar (no un `500` opaco — el
  fallo de deserialización se captura en `forecasting.load_model`); gracias a `forecaster.meta.json`,
  el mensaje nombra también la versión **de origen** que serializó el artefacto y cuándo.
- **Acción:** reentrenar (`make docker-pipeline` ya lo hace como parte del despliegue).
- **Regla:** no subir la versión menor del pin sin reentrenar el artefacto, y **entrenar siempre dentro
  del contenedor**: esta carpeta es un bind mount compartido, y un `vigia train` desde un entorno local
  con otra versión de scikit-learn deja el artefacto ilegible para el contenedor (los tests ya no pueden
  afectarlo: `ml/tests/conftest.py` los aísla en un directorio temporal).
