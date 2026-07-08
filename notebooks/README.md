# `notebooks/` — Exploración y evidencia reproducible

Esta carpeta documenta el trabajo de datos y de modelo en formato *notebook*, organizado en tres entregas
numeradas que reflejan el flujo real del proyecto: **explorar las fuentes → limpiar y unificar →
entrenar el modelo de pronóstico**. 

Los notebooks `002` y `003` **reutilizan el código de producción** mediante la importación de `vigia.etl.silver` 
y `vigia.ml.forecasting`, sin duplicar lógica. De este modo, el código presentado en los *notebooks* es 
el mismo que ejecuta el pipeline de producción.

## Índice de notebooks

| Orden | Notebook | Qué contiene | Duración aprox. |
|:---:|---|---|---|
| 1 | [001_Dataset.ipynb](001_Dataset.ipynb) | **Exploración inicial de las fuentes** (datos.gov.co/SODA2): inspección por dataset (homicidios, hurtos, extorsión…), volumen, esquemas y calidad del crudo. Genera los perfiles HTML de abajo. | ~depende de la API |
| 2 | [002_Limpieza_Silver.ipynb](002_Limpieza_Silver.ipynb) | **Limpieza y unificación (capa silver)**: las dos familias de esquema y los dos formatos de fecha, normalización DANE/DIVIPOLA, por qué **no se eliminan las filas repetidas** (con la evidencia sobre el dato) y la conciliación contra el informe de calidad versionado. | ~10 min |
| 3 | [003_Modelo_Pronostico.ipynb](003_Modelo_Pronostico.ipynb) | **Modelo de pronóstico**: features, entrenamiento real (`vigia.ml.forecasting.train`) con backtest walk-forward, métricas frente a las líneas base y lectura de resultados. | ~17 min (entrena el panel completo) |

## Perfiles de datos (`profiling_*.html`)

Los 20 archivos `profiling_<fuente>.html` contienen el **perfilamiento de datos de cada fuente**, generado
durante la fase de exploración del notebook `001`. Incluyen distribuciones, valores nulos, cardinalidades 
y otras estadísticas descriptivas. Se versionan como evidencia del análisis realizado durante la selección 
de fuentes y pueden abrirse directamente en cualquier navegador web.

## Cómo re-ejecutarlos

Requieren un `kernel` con el paquete instalado (`cd ml && pip install -e ".[dev]"`; la primera celda
de cada notebook agrega automáticamente la ruta del proyecto). También es necesario contar con información en las capas bronze/silver/gold del lago de datos (`make docker-pipeline`).

Los notebooks se pueden ejecutar nuevamente con *Jupyter* o mediante *nbclient*, por ejemplo:

```bash
cd notebooks && python -m jupyter nbconvert --to notebook --execute --inplace 002_Limpieza_Silver.ipynb
```

> [!NOTE]
> **Modo solo lectura para artefactos:** los notebooks están diseñados para **no sobreescribir** los artefactos
> generados por el pipeline. El *notebook* `002` reconstruye la capa *silver* únicamente en memoria, sin escribir 
> el archivo *Parquet* ni el informe de calidad. Por su parte el *notebook* `003` redirige el modelo entrenado al
> directorio `artefactos/` (una carpeta local no versionada, destinada a facilitar las pruebas de los *notebooks*)
> en lugar de `models/forecaster.joblib`. No eliminar las celdas que realizan dicha redirección.

> [!NOTE]
> **Las métricas pueden diferir ~1-3 %** respecto a las registradas en `reports/model_report.json`, debido a 
> diferencias en la versión de `scikit-learn` y al ruido numérico asociado a la ejecución multi-hilo. La ejecución
> de referencia es la del *pipeline* dentro de Docker. Este margen de tolerancia está documentado en el propio
> *notebook* `003`.
