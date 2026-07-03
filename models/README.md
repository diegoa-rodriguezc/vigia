# `models/` — Artefactos de modelo entrenados

Esta carpeta guarda los modelos **serializados** que sirve la API de ML. No se versionan en git
(son regenerables y pesados).

| Artefacto | Qué es |
|---|---|
| `forecaster.joblib` | El modelo de pronóstico: un `HistGradientBoostingRegressor` **global** (una sola instancia aprende de todas las series municipio × categoría) junto con su **metadata de entrenamiento** autoidentificable: `trained_at`, `seed`, `feature_cols`, métricas del backtest e importancias de features |

Las **métricas auditables** de la corrida que produjo el artefacto no viven aquí sino en
[reports/model_report.json](../reports/model_report.json), regenerado en cada entrenamiento.

## Cómo regenerar

```bash
make docker-pipeline    # pipeline completo dentro de Docker (incluye vigia train)
# o solo el entrenamiento, en local:
cd ml && python -m vigia train
```

Reproducibilidad: semilla global `SEED=77`. Las métricas pueden fluctuar **~1 % entre corridas** (el
*early stopping* del boosting es sensible a las reducciones de punto flotante multi-hilo); las
conclusiones cualitativas son estables — detalle en
[docs/CRISP-ML-Q.md](../docs/CRISP-ML-Q.md#3-ingeniería-del-modelo).

## ⚠️ El artefacto NO es portable entre versiones de scikit-learn

`scikit-learn` está fijado por versión menor (`>=1.9,<1.10` en `ml/pyproject.toml`) **a propósito**: un
`forecaster.joblib` serializado con una versión no se puede cargar con otra (cambian rutas internas y
`joblib.load` falla con errores como `ModuleNotFoundError: No module named '_loss'`).

- **Síntoma:** la API responde `503` con el mensaje accionable de reentrenar (no un `500` opaco — el
  fallo de deserialización se captura en `forecasting.load_model`).
- **Acción:** reentrenar (`make docker-pipeline` ya lo hace como parte del despliegue).
- **Regla:** no subir la versión menor del pin sin reentrenar el artefacto.
