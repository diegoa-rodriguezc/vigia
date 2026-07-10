# Metodología CRISP-ML(Q) en VigIA

VigIA se desarrolla siguiendo **CRISP-ML(Q)** — *Cross-Industry Standard Process for Machine Learning
with Quality Assurance*. A diferencia de CRISP-DM, CRISP-ML(Q) añade controles de **calidad** y
**riesgos** en cada fase y contempla explícitamente el **monitoreo y mantenimiento** del modelo en
producción. Este documento es la bitácora metodológica del proyecto.

| Fase | Estado | Artefacto / código |
|---|---|---|
| 1. Comprensión del negocio y los datos | ✅ | Este documento · `docs/ARCHITECTURE.md` |
| 2. Ingeniería de datos (preparación) | ✅ | `ml/vigia/etl/` |
| 3. Ingeniería del modelo | ✅ | `ml/vigia/ml/` |
| 4. Evaluación del modelo | ✅ | `ml/vigia/ml/evaluate.py` · `make train` |
| 5. Despliegue | ✅ | `ml/vigia/api/` · `docker-compose.yml` |
| 6. Monitoreo y mantenimiento | ✅ (diseño + monitoreo implementado: `vigia health`) | `docs/CRISP-ML-Q.md#6-monitoreo-y-mantenimiento` |

---

## 1. Comprensión del negocio y de los datos

**Objetivo de negocio.** Fortalecer las políticas públicas de seguridad y justicia mediante alertas
tempranas y pronósticos de criminalidad a nivel municipal, accesibles para entidades y ciudadanía.

**Magnitud del problema.** El crimen y la violencia le cuestan a Colombia el **3,64 % del PIB (~$68
billones/año, Fedesarrollo–BID 2022)**; la percepción de inseguridad alcanza el **52,9 %** (DANE, ECSC
2024) y la tasa de homicidios ronda **25 por 100.000 hab.** Reasignar **con anticipación** una fracción del
gasto hacia la prevención tiene alto retorno social y fiscal: ahí actúa VigIA (fuentes citadas en el
[README](../README.md#-impacto-escalabilidad-y-enfoque-territorial)).

**Criterios de éxito de negocio.**
- Pronósticos con error competitivo frente a las líneas base ingenuas que usa la evaluación —persistencia
  (último valor) y estacional (mismo mes del año anterior)—, medido con MAE y MASE en validación
  retrospectiva temporal (ver [4](#4-evaluación-del-modelo); el sMAPE se reporta como métrica complementaria).
- Anomalías verificables contra picos históricos conocidos.
- Asistente que responde con datos oficiales y cita su fuente.

**Datos.** 20 conjuntos de datos abiertos de datos.gov.co (API SODA2): **16** de eventos de la Policía
(catálogo *Seguridad y Defensa*) que forman la serie unificada —**13 de delito** y **3 de respuesta
institucional** (capturas, incautaciones, recuperaciones; separadas en gold)—, **2** administrativos
(auditorías, demandas) que alimentan el asistente como contexto de transparencia, **1** de referencia
oficial (**DIVIPOLA**, DANE) para nombres y coordenadas, y **1 de la Fiscalía General de la Nación**
(*otra entidad*) que aporta el eje de **Justicia** (ver abajo). Las 16 fuentes de eventos se seleccionaron
del *Asset Inventory* de la categoría (`uzcf-b9dh`, ~169 datasets consultados). Histórico desde 2003,
granularidad evento agregado por fecha×territorio×categoría. La composición —concentrada en el productor
oficial de la estadística delictiva y diversificada por entidad y modalidad donde hay señal distinta— es
una **decisión de diseño argumentada** en el README (§Datos abiertos utilizados) y en
[DATASETS.md](DATASETS.md#expansión-desde-el-asset-inventory-análisis-crítico). Ver
[DATA_DICTIONARY.md](DATA_DICTIONARY.md).

**Eje de Justicia (Fiscalía) — capa paralela.** Para no depender de una sola entidad y cubrir la *Justicia*
del reto, se incorpora *Procesos Fiscalía V3* (`dbdv-iihs`, ~23 millones de procesos) con su dimensión diferencial: **judicialización** (Indagación → Investigación → Juicio → Ejecución). **No se fusiona** con la
serie de la Policía (*proceso* ≠ *hecho registrado* → doble conteo): es una capa paralela
(`etl/justicia.py`). Como la agregación server-side no es viable a ese volumen (el backend revienta el
*timeout* en cualquier `$group`; un app token no lo arregla), se adquiere por **streaming keyset + agregación
local** (paginación continua por clave) — reproducible sin token (~15-25 min), con **reintento por página**
ante cortes de red (el avance no se pierde: la clave de paginación hace el reintento repetible) y colapso
periódico del acumulado (RAM acotada). El grano adquirido incluye el **título del Código Penal**
(`titulo_delito`, 24 valores — la taxonomía propia de la Fiscalía), lo que permite responder **"¿qué delito
se judicializa menos?"**: la tasa por título se publica en `gold/justicia_delito.parquet`,
`reports/justicia.json` (`tasa_por_delito`, con umbral mínimo de 10.000 procesos de etapa conocida para que
el ranking no lo dominen tasas de bajo volumen), el endpoint `/justicia/delitos`, la pestaña Justicia y las
data cards del asistente. Cifras reales y *Advertencias de uso* en
[DATA_DICTIONARY.md](DATA_DICTIONARY.md#capa-justicia--fiscalía-general-de-la-nación-fuente-de-otra-entidad-capa-paralela):
**tasa de judicialización nacional 8,49 %** (solo ~8,5 % de las noticias criminales superan la indagación);
por título penal, el extremo inferior es *Delitos Contra La Integridad Moral* (injuria/calumnia, **0,34 %**)
y el superior *Delitos Contra La Salud Pública* (**23,74 %**).

El reporte reproducible (`reports/justicia.json`) publica además tres bloques de **honestidad
metodológica**: (a) el **embudo por etapa cruda** de la cadena penal —no solo la clase binaria
indagación/judicializado—: Investigación 178.460, Juicio 862.535 y Ejecución de penas 926.136 (la etapa es
el *estado actual* del proceso, no un acumulado); (b) la **tasa por año del hecho** (`tasa_por_anio`), que
demuestra con el dato que las tasas agregadas mezclan cohortes 2004-2026: los años maduros rondan el
10-11 % y los recientes caen (2023: 5,85 %; 2026: 3,2 %) porque esos procesos aún no maduran — por eso las
tasas comparan territorios o delitos entre sí, no años recientes contra antiguos (advertencia declarada en
el reporte y en la pestaña Justicia); y (c) la **procedencia** bronze → gold: de 23.212.036 procesos
agregados se descartan 30.547 (**0,13 %**, por causa: sin municipio válido o año fuera de rango). La
ingesta por streaming quedó **conciliada contra el servidor** (2026-07-10): `count(1)` server-side =
23.212.036 = suma local, **diferencia 0** — el keyset leyó exactamente cada fila; las próximas re-ingestas
registran ese linaje en el meta del bronze (`source_rows`/`source_count`).

**Alineación estratégica.** Las fuentes priorizan el conjunto que la **Hoja de Ruta Nacional de Datos
Abiertos Estratégicos 2025-2026** (`fn2v-r4gu`, categoría DEFENSA, id 70) marca como prioritario para el
reto: *"Seguridad y justicia – Estadísticas de criminalidad"*. Su recomendación oficial es *consolidar
todos los delitos*, justo lo que ejecuta la capa *silver* (16 fuentes de eventos → modelo único; las 13 de
delito materializan la recomendación). Mapeo
verificado en [DATA_DICTIONARY.md](DATA_DICTIONARY.md#alineación-con-la-hoja-de-ruta-nacional-de-datos-abiertos-estratégicos-2025-2026).

**Riesgos y controles de calidad (QA).**
- *Calidad de fuente:* formatos de fecha y esquemas heterogéneos → unificación validada en *silver*.
- *Sesgo de subregistro:* los datos reflejan delitos **denunciados/registrados**, no la criminalidad
  real. Documentado y comunicado en la UI.
- *Cobertura territorial desigual:* municipios con pocos registros → el modelo agrega y marca baja
  confianza.

## 2. Ingeniería de datos (preparación)

- **Capa bronze (`etl/bronze.py`).** Descarga fiel del crudo a Parquet con metadatos de linaje
  (fuente, fecha de ingesta, nº de filas, hash).

- **Capa silver (`etl/silver.py`).** Controles de calidad aplicados:
  - Interpretación robusta de fechas (ISO y `dd/mm/yyyy`) → rechazo/registro de fechas inválidas.
  - Normalización de códigos DANE a 5 dígitos (municipio) y 2 (departamento).
  - Normalización de texto (mayúsculas, *trim*, remoción de sufijos `(CT)`).
  - Tipado de `cantidad` a entero; descarte de negativos.
  - Unificación al esquema de eventos común, **conservando el grano del publicador — sin
    eliminar filas repetidas**. La decisión está medida, no asumida: en las fuentes a grano de evento
    (`cantidad`≈1) dos hechos del mismo día/municipio con los mismos atributos producen filas
    idénticas **legítimas**, porque el esquema publicado es estrecho (6-11 columnas). Tres
    evidencias lo confirman: (1) las fuentes que el publicador entrega pre-agregadas
    (`cantidad`>1: hurto a personas, hurto de vehículos, violencia intrafamiliar) traen **0 filas
    repetidas** — la repetición solo existe donde el grano es evento; (2) la serie anual de
    homicidios **con las filas repetidas conservadas reproduce la cifra oficial** de la Policía
    (2023 ≈ 13,6 mil), mientras que al eliminarlas queda un 15-30 % por debajo; (3) la paginación SODA2 es estable
    (`$order=:id`) y no reintroduce filas. Una versión anterior del pipeline aplicaba un
    `drop_duplicates()` global que borraba ~30 % de las filas (homicidios −21 %, capturas −66 %):
    era subconteo sistemático y se retiró. La conciliación crudo→silver por fuente queda
    auditable en `reports/silver_quality.json` (bloque `procedencia`).
  - **Controles de calidad** (`etl/quality.py`): completitud por columna, **`placeholders_pct`** (% real de
  `NO REPORTADO` por campo, para no sobrevender el 100 % estructural), rango de fechas, conteos de fuentes y
  *checks* de nulos/cantidades≤0/fechas futuras, **y una alerta por cada fuente truncada en la ingesta**
  (si se fija `SODA_MAX_ROWS` para pruebas: el linaje del bronze marca `capped`/`row_cap` y el informe lo
  eleva a alerta de volumen parcial, de modo que una ejecución incompleta nunca se lea como el total). Se
  emite un informe por ejecución en
  `reports/silver_quality.json`. `placeholders_pct` detecta los campos de texto sea cual sea su dtype
  (`object` o pandas `StringDtype`, que es como silver convierte el tipo del texto). El resultado **expone el subregistro real** que el 100 % estructural oculta: en la ejecución de referencia, **`zona` ≈87 %, `arma_medio` ≈82 %, `grupo_etario` ≈43 % y `sexo` ≈34 %
  de valores `NO REPORTADO`** — un dato de calidad relevante para no sobreinterpretar esas dimensiones;
  VigIA además **no** las desglosa, por decisión ética (ver [Ética y uso responsable](#ética-y-uso-responsable)).

- **Capa gold (`etl/gold.py`).** Agregación a serie mensual `municipio × categoría` + *features* de
modelado: rezagos, medias/desviaciones móviles, calendario (estacionalidad y tendencia) y **features de
identidad de la serie** (media histórica con **ventana de 60 meses** —no expansiva: sobre 20+ años
arrastraría el nivel de épocas superadas en series con caída secular, ver bitácora Iteración 12— y meses
activos), que dan al modelo global el nivel
base propio de cada serie sin fuga de datos.

### Limitaciones del dato de origen (declaradas)

Cuatro propiedades de la fuente que el usuario del modelo debe conocer; ninguna se «corrige» en el dato
(se declaran y se acotan por diseño):

1. **Expansión del registro, no de la criminalidad (medida).** El volumen nacional de delitos
   registrados pasa de **258.315 (2014) a 650.934 (2019): +152 % en cinco años**. Ese salto refleja la
   consolidación de los sistemas de registro de la Policía (SIEDCO y la denuncia virtual «A Denunciar»,
   ~2017-2019) mucho más que un cambio real de la criminalidad: la serie histórica larga **no es de
   nivel comparable** entre décadas. El diseño lo amortigua sin retocar el dato: la media histórica del
   modelo usa una **ventana de 60 meses** (no arrastra el nivel de épocas con otro régimen de registro,
   Iteración 12) y la deriva del monitoreo compara contra una **referencia *rolling*** (no contra toda
   la historia). No se intenta «corregir» la serie hacia atrás: sería inventar una historia alternativa
   sin verdad-terreno contra la cual validarla.
2. **Huecos internos = cero hechos registrados (supuesto declarado).** `gold` construye el calendario
   mensual de cada serie **solo sobre su propio rango activo** (no inventa años fuera de él) y rellena
   con 0 los meses internos sin filas: el supuesto es «sin fila = sin hecho registrado», razonable
   porque las fuentes están a grano de evento. Un mes interno vacío por falla del publicador se leería
   como cero real — riesgo residual que el detector de anomalías mira hacia picos (z alto), no hacia
   ceros, y que la señal de frescura del monitoreo acota en el extremo final.
3. **Los meses finales llegan incompletos (rezago de reporte).** El entrenamiento **no los trunca**: el
   rezago varía por fuente y truncar un número fijo de meses descartaría dato bueno. El control es
   compensatorio: la pestaña *Salud del modelo* vigila la frescura y el **cambio de volumen reciente**
   (la señal amarilla de deriva de la ejecución de referencia es exactamente este fenómeno) y la
   política de reentrenamiento mensual (§6.4) reabsorbe los meses a medida que se completan.
4. **Backtest con 3 orígenes temporales (declarado y complementado).** El backtest de entrenamiento usa
   3 orígenes × horizonte 6 — pocos orígenes, pero sobre el panel completo: **30.606 puntos de prueba**
   por ejecución. Más orígenes multiplican el costo (cada origen re-entrena y recalcula features del
   panel entero). El complemento es el **backtest extendido a 12 meses** del monitoreo (§6.2), que
   valida el horizonte largo con orígenes adicionales fuera del ciclo de entrenamiento.

## 3. Ingeniería del modelo

> Un solo modelo aprende de *todas* las series de criminalidad a la vez. En vez de memorizar
> cada municipio por separado, se apoya en el nivel histórico y las tendencias recientes de cada serie para
> proyectar los próximos meses, y acompaña cada pronóstico con una banda que indica cuánta incertidumbre hay.

- **Pronóstico:** modelo global de *gradient boosting* sobre todas las series con *features* de rezago,
  estacionalidad e identidad de serie. Devuelve además una **banda de incertidumbre (~80 %)** derivada de
  la dispersión robusta de los residuos del backtest, ensanchada con el horizonte (error recursivo
  acumulado). Justificación: robusto, sin dependencias pesadas, reproducible con semilla fija (`SEED=77`).
- **Anomalías:** z-score robusto (MAD) sobre el residuo estacional **por serie** + `IsolationForest`
  sobre features **normalizadas por serie** (consenso de dos señales). La normalización evita que los
  municipios de mayor volumen acaparen las alertas. **Solo se alertan categorías de delito:** las series
  de *respuesta institucional* (capturas, incautaciones, recuperaciones) se excluyen, porque un repunte
  ahí es un buen resultado operativo, no un riesgo ciudadano (clasificación en `vigia/datasets.py`,
  `RESPONSE_CATEGORIES`).
- **Reproducibilidad:** semilla global (`SEED=77`), linaje de datos por hash, artefactos serializados en
  `models/` con su metadata de entrenamiento. **Alcance honesto:** el **pipeline de datos** (bronze→silver→
  gold) es **determinista bit-a-bit**. El **modelo** lo es *salvo ruido numérico ~1 %* entre ejecuciones: aunque
  todas las fuentes de azar están sembradas (`random_state=SEED` en el HGB y en la importancia por
  permutación, RNG sembrado en el muestreo), el `HistGradientBoostingRegressor` con `early_stopping='auto'`
  corta según un score de validación sensible a las reducciones de punto flotante **multihilo** (OpenMP, no
  asociativas) → el nº de iteraciones y las métricas fluctúan ~1 % entre ejecuciones (p. ej. el MAE a 1 paso,
  **2,5453** en el reporte vigente, se mueve unas centésimas de una ejecución a otra). **Advertencia — amplificación del ruido:** en las métricas derivadas de la **diferencia entre
  dos cantidades casi iguales** —el caso del *skill* frente a la persistencia a 1 paso— ese ~1 % del MAE se
  traduce en **puntos porcentuales** del margen (entre ≈+1 y ≈+3 % según la ejecución); por eso la
  documentación cita esa cifra como **banda**, no como valor puntual, y la cifra exacta de la ejecución
  vigente vive solo en el reporte versionado. **Las
  conclusiones cualitativas son estables** (supera a **ambas** líneas base en MAE a 1 paso y multipaso, y a
  la persistencia también en MASE; el empate práctico con la estacional en sMAPE multipaso y los veredictos
  por tercil se mantienen entre ejecuciones). Forzar un solo hilo (`OMP_NUM_THREADS=1`) debería **reducir o eliminar**
  esa fluctuación numérica (al quitar las reducciones multihilo), a costa de un entrenamiento mucho más lento; se deja como opción para quien requiera reproducir cifras exactas, no como el camino por defecto.

## 4. Evaluación del modelo

> Para saber si el modelo sirve, lo probamos "viajando al pasado": lo entrenamos solo con
> datos antiguos y le pedimos que adivine meses que ya conocemos, comparándolo con dos reglas ingenuas
> ("repetir el último dato" y "el mismo mes del año pasado"). Todas las métricas de abajo (MAE, MASE, sMAPE)
> salen de ese ejercicio: cuanto más bajas, mejor. La conclusión honesta es que el modelo **gana a ambas
> reglas en error absoluto (MAE)** al proyectar varios meses —que es lo que se usa—, con margen amplio sobre
> "repetir el último dato" y más ajustado sobre "el mismo mes del año pasado"; y que el sMAPE alto que se ve
> es un **artefacto** de contar hechos casi nulos, no un error real del pronóstico.

- **Backtesting walk-forward RECURSIVO (rolling origin), sin fuga:** para cada uno de los últimos
  `n_splits` orígenes se entrena solo con el pasado y se pronostica el horizonte completo (`test_months`,
  por defecto 6) **de forma recursiva — igual que en producción —**, comparando contra los valores reales.
  Así se valida el **horizonte que de verdad se entrega al usuario**, no solo 1 paso (`ml/vigia/ml/forecasting.py`,
  `_walk_forward`).
- **Métricas:** MAE, **MASE** y sMAPE del modelo frente a **DOS líneas base ingenuas** —la **persistencia**
  (último valor arrastrado por el horizonte) y la **estacional-ingenua** (mismo mes del año anterior, `tp−12`,
  una vara **más exigente** en series con estacionalidad marcada)—, reportadas (a) **a 1 paso** —comparables,
  *headline*— y (b) **multipaso** agregado + **por paso** (degradación del error con el horizonte). Cada
  ejecución persiste un reporte reproducible en **`reports/model_report.json`** (`ml/vigia/ml/evaluate.py`).
- **MASE, la métrica de cabecera para conteos (y por qué el sMAPE engaña):** el **sMAPE** de estas series
  ronda **>100 %** (≈127 % a 1 paso) — **no** es "127 % de error" sino un **artefacto**: en conteos casi nulos
  (0/1) el denominador `|y|+|ŷ|` colapsa y el sMAPE se satura cerca de su tope (200 %). Por eso la métrica
  primaria es el **MASE** (*Mean Absolute Scaled Error*, Hyndman): el MAE **escalado por el MAE ingenuo
  1-paso _dentro de muestra_ de cada serie**, adimensional y comparable entre territorios. El MASE del modelo
  (**≈1,35** a 1 paso, **≈1,48** multipaso) queda **por debajo** del de la persistencia (**≈1,45 / ≈1,66**);
  el reporte **no publica el MASE de la estacional** — frente a ella la comparación se hace en MAE. Que el
  MASE sea **>1** es honesto —pronosticar fuera de muestra estos conteos ruidosos
  es más difícil que el naive dentro de muestra—; lo relevante es que el modelo **bate a la persistencia en la
  misma escala**. *Skill* en MAE: **+1 a +3 % según la ejecución** vs. persistencia (banda por el ruido
  multihilo, ver [Reproducibilidad](#3-ingeniería-del-modelo)) y ≈**+6 %** vs. estacional a
  1 paso; ≈**+16 %** / ≈**+9 %** multipaso (`skill_mae_vs_*` en el reporte, con la cifra exacta vigente).
- **Desglose por volumen de serie (`por_volumen`):** MAE/sMAPE/MASE del modelo vs. líneas base por **tercil de
  volumen mensual**. Reconcilia la lectura del agregado: en el tercil de **volumen ínfimo** (conteos
  esporádicos donde el error absoluto es diminuto y domina el agregado) **ambas** líneas base son imbatibles
  —la persistencia y, aún mejor, la estacional— y el modelo **no gana** (MASE ≈1,88, el peor); en el tercil
  **medio** gana con holgura en MAE y sMAPE (≈0,90 vs ≈1,03 persistencia / ≈1,01 estacional; MASE ≈1,16); y en
  el **alto** también gana: a la estacional con holgura (≈6,23 vs ≈6,64) y a la persistencia por margen fino
  (≈6,23 vs ≈6,25 — puede oscilar entre ejecuciones), con **MASE ≈1,01, el mejor** y clara ventaja en sMAPE
  (≈75 vs 83). El flag `gana_modelo` por tercil lo registra explícitamente. El valor del modelo se concentra
  donde hay **señal recurrente** (volumen medio/alto, justo donde importa la planeación preventiva); en las
  series ultra-dispersas el naive es casi óptimo **por construcción** y no hay margen que ganar.
- **Calibración de la incertidumbre (conformal):** la banda conserva su forma heteroscedástica
  (`√(φ·nivel)·√paso` — escala con el nivel de cada serie y crece con el horizonte), pero su **escala se
  calibra empíricamente** en vez de asumir el cuantil normal: `pi_scale` es el **cuantil al 80 % de los
  residuos estandarizados out-of-fold** del backtest (residuos genuinamente OOS, cada origen entrena solo
  con el pasado). Así la cobertura iguala el nivel nominal **por construcción y de forma honesta**. *Efecto
  medido:* antes se asumía el cuantil normal (`1,2816`), que con la dispersión cuasi-Poisson inflada por las
  series de alto volumen daba una banda **demasiado ancha** —cobertura empírica **94,4 %** frente al 80 %
  nominal, fuera del rango [70 %, 90 %] de [6.2](#62-deriva-de-concepto--degradación-del-modelo)—; tras la calibración `pi_scale ≈ 0,67` y la cobertura cae a
  **80,0 %** (1 paso y multipaso), dentro de umbral. El punto del pronóstico (MAE/sMAPE) no cambia: la
  calibración solo dimensiona el ancho del intervalo. **Acotación (para no sobreafirmar):** la cobertura del
  80,0 % se mide sobre el **mismo backtest** con el que se calibró `pi_scale` — los residuos son out-of-fold
  respecto al modelo, pero calibración y verificación comparten datos, así que la cobertura iguala el nominal
  **por construcción**, no como validación independiente de la banda. Una validación estricta exigiría
  calibrar en unos orígenes y medir la cobertura en otros (pendiente declarado, no una omisión encubierta).
- **Interpretabilidad (`interpretabilidad.features`):** importancia de features por **permutación**
  (`sklearn.inspection.permutation_importance`, puntuación = −MAE) sobre una muestra del conjunto modelado.
  El `HistGradientBoostingRegressor` no expone `feature_importances_`; la permutación es agnóstica al
  modelo y mide cuánto **se degrada el MAE al barajar cada feature**. Resultado explicable y auditable (ejecución
  actual): domina la **media móvil anual** (`roll_mean_12`, ≈1,30), seguida del **nivel de la serie en su
  ventana histórica** (`media_hist`, ≈0,66 — más informativa desde que es una ventana de 60 meses y no la
  media de toda la historia), el último mes (`lag_1` ≈0,14), la media móvil corta (`roll_mean_3` ≈0,13) y la
  semestral (`roll_mean_6` ≈0,12). Es decir, **el modelo se apoya en el nivel y la tendencia suavizada
  de cada serie**, no en los rezagos crudos individuales: los `lag_2…lag_12` y las desviaciones móviles tienen
  importancia ~0 (redundantes con las medias móviles), y del calendario solo `mes` aporta de forma
  moderada (`mes_sin`/`mes_cos`/`trimestre`, ~0). Esto hace **auditable** en qué se apoya cada pronóstico, no una caja negra.
- **sMAPE:** promedio **simple** (no ponderado) sobre las series con historia suficiente. Se conserva por
  comparabilidad, pero **no** es el criterio primario (ver el artefacto arriba): el titular es el **MASE**.
- **Criterio de aceptación (múltiple, no una sola métrica):** el modelo debe (a) superar a la persistencia en
  **sMAPE multipaso** —el horizonte que efectivamente se entrega, 6 meses recursivos— (`supera_linea_base_smape_multipaso`);
  y hoy además (b) la bate en **MAE y MASE a 1 paso y multipaso** (`supera_linea_base_mae`) y (c) supera a la
  **estacional-ingenua** en MAE a 1 paso y multipaso (`supera_linea_base_estacional_mae[_multipaso]`).
  **Dónde cede (declarado):** el sMAPE a 1 paso (≈127 vs ≈120 — el artefacto de los conteos ~0 ya explicado,
  no una debilidad real del pronóstico), los **pasos 2-3 en MAE frente a la estacional** (3,07 vs 2,89 en el
  paso 2 — la ventaja sobre esta línea base no es monótona por paso), el tercil de volumen ínfimo (ver
  `por_volumen`) y un **sobrenivel residual en el homicidio metropolitano** (≈+40 % sobre la media reciente
  en Bogotá; era el doble antes de la Iteración 12, que lo redujo con la ventana de `media_hist` — límite
  declarado de un modelo global sobre series con caída secular).
  La ventaja **crece con el horizonte frente a la persistencia**, que es justo lo que se entrega. A estas
  cesiones del modelo se suman las **limitaciones del dato de origen** (expansión del registro 2014-2019,
  huecos internos, rezago de reporte, 3 orígenes del backtest), declaradas y acotadas en la
  [§2](#limitaciones-del-dato-de-origen-declaradas).

**Validación de la detección de anomalías.** No se evalúa por error sino por **precisión/recall contra picos
inyectados** (ground truth) en un panel sintético (`tests/test_anomaly.py`,
`test_benchmark_precision_recall_*`):
- En el **régimen realista** (anomalías raras, ~1–2 % de los meses-serie) el detector recupera casi todos los
  picos con **precisión ≥0,85 y recall ≥0,9**.
- Cuando las anomalías son **más densas que `contamination`**, sacrifica recall **antes** que precisión
  (precisión se mantiene ~1,0): comportamiento operativo deseable — pocas alertas, casi todas verdaderas.
- **Justificación de `contamination=0,03`:** fija la prevalencia *esperada* de outliers del IsolationForest;
  el **consenso** de dos señales (z robusto **y** bosque) + el filtro de *solo picos al alza* la tensan aún
  más, de modo que la **tasa real** de alertas queda **muy por debajo** de ese 3 %. El reporte
  (`anomalias.tasa_alertas_pct`, `alertas_por_serie`) lo evidencia: el total (30.243) es **≈1 % de los
  meses-serie** evaluados (1,13 %) y representa un **catálogo histórico desde 2003** (≈2 alertas por serie
  en ~20 años), no un muro de alertas simultáneas. Las perillas (`contamination`, `z_threshold`) están expuestas en
  `anomaly.detect` para ajustar el punto de operación sin tocar el código.

**Validación sobre anomalías REALES** (`ml/vigia/ml/anomaly_validation.py`, `vigia validate-anomalies`). El
benchmark anterior usa ground truth sintético; como **no hay contacto con entidades** que aporte una
verdad-terreno oficial, se añaden dos validaciones sobre las anomalías reales:
- **Contra un catálogo de eventos documentados** (recall@ventana): se mide qué fracción de un catálogo de
  hitos públicos **verificados** (municipio, mes, categoría) cayó **dentro de ±N meses** de una anomalía. El
  catálogo (`docs/eventos_documentados.csv`, configurable por `VIGIA_EVENTS_CATALOG`; plantilla vacía en
  `…example.csv`) es un **insumo externo y versionado** —no hechos quemados en el código—, con sus códigos
  DANE verificados contra DIVIPOLA y cada fila citando su fuente (prensa/Comisión de la Verdad/CNMH). La
  validación está **cableada al pipeline** (`vigia pipeline` la regenera; degrada con elegancia si el
  catálogo no está montado). El reporte emite **dos modos** para no sobrevender los aciertos triviales de las
  metrópolis (donde casi todo mes tiene *alguna* anomalía): *por municipio-mes* y *exigiendo además que
  coincida la categoría*. **Resultado sobre el catálogo de referencia (11 hitos, 2003-2025, ±1 mes):**
  **recall 1,0 por municipio-mes (11/11)** y **0,64 exigiendo categoría (7/11)**. El detector captura los
  deterioros municipales reales —los enfrentamientos de **Arauca 2022** (Tame, Saravena, Arauquita), la
  **crisis del Catatumbo 2025** (Tibú, El Tarra), la **masacre de Samaniego 2020**, el **Club El Nogal 2003**,
  la **Brigada 30 de Cúcuta 2021** y la **chiva bomba de Toribío 2011** (el único fallo histórico: lo
  silenciaba el punto ciego MAD=0 que corrigió la Iteración 13 — su serie de TERRORISMO tiene la mayoría de
  los meses en cero y el z quedaba forzado a 0). En el modo
  estricto por categoría caen los atentados **pequeños frente a la línea base de una metrópoli**
  (Andino, Escuela General Santander: aciertan por municipio-mes vía el deterioro concurrente de otra
  categoría, no por la propia). No es prueba causal: es **validez de cara**, con sus límites declarados. *(La
  corrección del subconteo de la Iteración 11 elevó este recall de 7/11 a 10/11 — al eliminar erróneamente
  las filas repetidas se perdían precisamente los picos de hechos que estos eventos generan— y la del punto
  ciego MAD=0 de la Iteración 13 lo llevó a 11/11.)* La corroboración interna (abajo)
  opera sobre las anomalías reales.
- **Corroboración interna** (sin datos externos): fracción de anomalías respaldadas por **otra categoría de
  delito en el mismo municipio-mes**. Un deterioro real suele ser multidelito; un artefacto aislado, no.
  *Resultado sobre el catálogo actual (30.243 anomalías): **24,6 % corroboradas** (7.433 anomalías respaldadas
  por otra categoría, agrupadas en 3.453 clústeres multidelito)* — muy por encima de lo esperable si las
  alertas fueran ruido aislado. NO es prueba causal:
  es **validez de cara**, declarada como tal. Reporte en `reports/anomaly_validation.json`.

**Evaluación del asistente (RAG/agente).** El componente de IA generativa también se mide, no solo se
guarda con rieles (`ml/vigia/rag/evaluation.py`, CLI `vigia rag-eval`, reporte reproducible en
[`reports/rag_eval.json`](../reports/rag_eval.json)). Las **preguntas de referencia** —preguntas cuya
respuesta correcta se conoce de antemano— **se derivan de gold/reports en el momento de evaluar**:
municipios, categorías y cifras esperadas salen de los mismos artefactos que alimentan
las data cards y las herramientas del agente, así que no hay respuestas quemadas que caduquen con la
actualización mensual. Se puntúan cuatro señales sin juicio humano:
- **Exactitud de cifras:** la respuesta contiene la cifra esperada (totales por municipio, conteos
  nacionales por categoría y año, superlativos de ranking, tasa y volúmenes de la capa Justicia, y el
  conteo de una fuente de **transparencia institucional** —demandas notificadas a la Policía—; el
  comparador tolera los separadores de miles y el decimal con coma o punto).
- **Abstención correcta:** ante preguntas **fuera del alcance** (capital de Francia, precio del dólar,
  elecciones…) o municipios inexistentes, el asistente debe **rehusar sin inventar cifras** — es el
  guardarraíl anti-alucinación convertido en métrica.
- **Citación:** las respuestas que aciertan la cifra deben traer al menos una fuente (trazabilidad).
- **Resolución difusa:** un municipio con error de tipeo ("Medallin") debe resolverse al oficial y
  responder con su cifra.
Evalúa el **camino de producción** y funciona con **ambos modos** del asistente: agente con herramientas
(proveedor openai/anthropic) y RAG clásico (p. ej. Ollama local, más lento); `--modo clasico|agente|auto`
permite forzar y comparar, y el reporte registra el modo real de cada respuesta. El arnés está probado
sin BD ni LLM (`tests/test_rag_evaluation.py`, respuestas inyectadas); la evaluación real exige la base
indexada y el proveedor activos (`make docker-rag-eval`).

**Ambos caminos quedan medidos y versionados**, cada uno con su reporte (la opción `--out` evita que una
evaluación sobrescriba la otra): con el **agente + proveedor gestionado** el asistente alcanza el 100 %
en las tres señales con ~7 s por pregunta ([`reports/rag_eval.json`](../reports/rag_eval.json)); por el
**camino por defecto** —Ollama local + RAG clásico, el despliegue sin clave de API— alcanza el 88,2 % de
exactitud, el 71,4 % de abstención correcta y el 100 % de citación, con ~77 s por pregunta en CPU
([`reports/rag_eval_ollama.json`](../reports/rag_eval_ollama.json), `make docker-rag-eval-ollama`). La
medición del camino local dejó lecciones de método, aplicadas y verificables: (1) el **detector de
abstención** del arnés se amplió con las formas pasivas con que rehúsa el LLM local («la respuesta no
puede ser proporcionada», «el contexto no incluye/contiene/menciona…»), detectadas al revisar las
respuestas literales de los falsos fallos — el guardarraíl SÍ rehusaba; el detector no reconocía esa
redacción; (2) **`OLLAMA_TEMPERATURE=0` quedó fijado por medición**: con 0,2 el modelo cambiaba de
respuesta entre ejecuciones (un ranking acertado pasaba a fallar) y tardaba ~50 % más — el mismo criterio
que ya fijó `LLM_TEMPERATURE=0` en los proveedores gestionados; (3) la **redacción de las data cards es
parte de la calidad de la recuperación**: al añadir las cards por título penal, repetir en ellas el
sintagma «tasa de judicialización nacional» desplazaba a la card nacional del contexto y el asistente
citó la tasa de un título como si fuera la del país — se corrigió reformulando las cards nuevas (la
medición lo confirmó); (4) los **fallos del camino local quedan declarados** en el detalle del reporte:
el total nacional de procesos de la Fiscalía (cita las fuentes pero no entrega la cifra), un ranking que
el modelo local pequeño (qwen3:1.7b) lee mal con la base de conocimiento ampliada, y dos preguntas fuera
de alcance que responde en vez de rehusar («la capital de Francia», el precio del dólar), sin llegar a
inventar cifras de datos. La comparación honesta entre caminos —100 % gestionado vs 88/71 local— es en
sí misma un resultado: el guardarraíl por herramientas del agente es más disciplinado que el RAG clásico
con un LLM de 1,7B.

### Bitácora de iteración (hallazgos reales)

> El rigor no es presentar un número bonito, sino documentar cómo se llegó a él.

- **Iteración 0 (datos sintéticos densos):** el modelo superó a la línea base (sMAPE 75 vs 80) —
   verifica que la mecánica de *features* y *backtesting* es correcta.
- **Iteración 1 (muestra real truncada, 8.000 filas):** el modelo **perdió** contra la línea base
   (sMAPE 185 vs 165). *Causa raíz detectada:* la capa gold rellenaba un **calendario global**
   (2003→hoy) para todas las series, inventando años de ceros a municipios que solo aparecen tarde;
   esto corrompe el modelo e infla el sMAPE (indefinido con valores ≈0).
- **Corrección (tras la Iteración 1):**
    - (a) recortar el calendario al **rango activo de cada serie**; 
    - (b) **filtrar series con poca historia no nula** (donde el pronóstico no aporta y la línea base es imbatible). Tras esto la muestra truncada quedó demasiado pequeña para evaluar → se confirma que **se requiere ingesta de datasets completos** para un backtest representativo (la muestra de 8.000 filas tomaba solo los primeros IDs, sesgados a 2003).
- **Iteración 2 (datasets completos):** con el calendario por serie corregido, sobre el universo real
   *de entonces* (**1.118 municipios DANE**, ~4,6 millones de hechos; ~7.400 series con ≥12 meses de actividad —
   **cifras históricas de esta iteración, con el catálogo de 8 datasets**; el universo vigente tras ampliar
   a 16 fuentes es mayor en series y hechos: 1.106 municipios modelados, 13.089 series, 12,98 millones de hechos, ver **Estado actual**),
   el modelo **supera a la línea base en sMAPE** (≈97 vs ≈111). **Honestidad
   metodológica:** en **MAE absoluto el modelo NO bate a la línea base ingenua** (≈2,6 vs ≈2,4): "repetir
   el último valor" es muy difícil de superar en series estables de alto volumen. El aporte del modelo
   está en el error relativo (sMAPE) y en aportar pronóstico donde la serie tiene estructura estacional.
- **Iteración 3 (pérdida de Poisson):** se probó `loss="poisson"` por ser principista para conteos,
   pero su enlace logarítmico extrapolaba y **disparó el MAE** en algunas series → se **revirtió** a
   pérdida cuadrática (más estable). *Decisión basada en evidencia, no en intuición.*
- **Iteración 4 (identidad de serie + incertidumbre):** se añadieron features de **nivel histórico**
   (media expansiva y meses activos por serie), que dan al modelo global la escala propia de cada
   municipio×categoría; y una **banda de incertidumbre cuasi-Poisson** que escala con el nivel de la
   serie (un σ global producía intervalos absurdamente estrechos en series de alto volumen). La detección
   de anomalías pasó a usar features **normalizadas por serie** en el IsolationForest, eliminando el sesgo
   hacia municipios de alto volumen (efecto medible: pasó a detectar también picos relativos en series
   pequeñas, subiendo el total de alertas; la calibración del punto de operación se valida en la Iteración 7).
- **Iteración 5 (catálogo ampliado + walk-forward):** el catálogo de eventos creció de 8 a **16 datasets**
   (seleccionados del *Asset Inventory* `uzcf-b9dh`), incorporando los delitos urbanos de mayor preocupación
   ciudadana (hurto a personas/residencias, delitos sexuales/informáticos, extorsión, secuestro, terrorismo,
   trata). El backtesting pasó de un **holdout único** a **walk-forward (rolling origin, 3 folds)** —promedia
   varios orígenes temporales, más robusto que un solo corte— y el modelo final se **reentrena con todo el
   histórico** (antes descartaba los últimos meses reservados al test). *Efecto en las métricas (snapshot de
   esa ejecución, a 1 paso):* el modelo mostraba ventaja en sMAPE (≈72 vs ≈101) y una **brecha en MAE** que se
   ensanchaba (≈6,1 vs ≈2,5): las nuevas series urbanas son de **alto volumen y fuerte autocorrelación
   mensual**, donde "repetir el último valor" es aún más difícil de batir en error absoluto. **Reconciliación
   con la ejecución actual (catálogo completo + periodo extendido a 2026-05):** al descargar el histórico
   completo, la ventaja en sMAPE **a 1 paso** se estrechó y **se revirtió** (hoy ≈126 vs ≈118, la persistencia
   a corto plazo es muy fuerte); la ventaja del modelo se **concentra en el horizonte multipaso** (sMAPE
   ≈113 vs ≈115) y en el **tercil de volumen medio**. El diagnóstico de fondo se mantiene: el aporte del
   modelo es el error **relativo** y la **proyección a varios meses**, no el error absoluto a 1 mes. Las
   categorías derivadas de texto se unificaron a una **convención canónica** (guion bajo), consistente en todo el stack.

- **Iteración 6 (validación multipaso + reconciliación del MAE):** dos refuerzos de rigor pedidos por una
   autoevaluación crítica. 
   - (a) **Validar el horizonte que se entrega:** el backtest a 1 paso no decía nada del
   pronóstico recursivo a 6 meses que ve el usuario. Se reescribió el backtest a **walk-forward recursivo
   multipaso** (espeja `predict`): reporta el error agregado del horizonte, su **degradación por paso** y la
   **cobertura empírica de la banda** de incertidumbre. *Hallazgo:* contra la **persistencia multipaso** el
   modelo gana en **sMAPE** con holgura **creciente** por paso (la línea base se degrada rápido con el
   horizonte, el modelo mucho menos), confirmando el valor del pronóstico más allá de 1 mes; en **MAE
   absoluto** la persistencia sigue siendo difícil de batir también en multipaso (el aporte del modelo está
   en el error **relativo**). 
   - (b) **Reconciliar el MAE:** el desglose `por_volumen` (terciles) muestra que la
   "derrota" en MAE agregado se concentra en los tramos de **volumen ínfimo y alto** —donde "repetir el último
   valor" es casi imbatible en error absoluto—; en el tramo de **volumen medio** el modelo gana en **ambas**
   métricas y en el **alto** gana en **sMAPE**. Además se corrigió un **parámetro muerto**: `test_months` ahora **gobierna el horizonte validado** (antes se reportaba sin efecto). 
   - (c) **Interpretabilidad:** se añadió **importancia por permutación** al reporte (`interpretabilidad.features`), que hace auditable en qué señales se apoya el modelo (dominan la **media móvil anual** `roll_mean_12` y el **nivel histórico** `media_hist`; los rezagos crudos `lag_2…lag_12` resultan redundantes). Todo cubierto con tests sintéticos offline (`test_forecasting.py`).
- **Iteración 7 (validación y calibración de anomalías):** se cerró la crítica sobre el volumen de alertas.
   - (a) **Benchmark de precisión/recall** por **inyección de picos conocidos** en un panel sintético
   (`test_anomaly.py`): precisión ≥0,85 y recall ≥0,9 en el régimen de anomalías raras; la precisión se
   mantiene ~1,0 al densificar, sacrificando recall de forma predecible (acotado por `contamination`).
   - (b) **Reframe del volumen:** el reporte añade `tasa_alertas_pct` y `alertas_por_serie`
   (`evaluate._anomaly_stats`), mostrando que el total absoluto es **<1 % de los meses-serie** evaluados — un
   catálogo histórico desde 2003, no alertas simultáneas. 
   - (c) **Justificación de `contamination=0,03`** y de
   las perillas de operación. Todo con tests offline.
- **Iteración 8 (población exógena, tasas por 100.000 habitantes y mezcla con persistencia):** se atacó de raíz la crítica
    más dura —el modelo **perdía ~2× en MAE** contra la persistencia (5,02 vs 2,57 multipaso)— con tres
    cambios encadenados, cada uno **medido** antes de cablearlo. 
    - (a) **Señal exógena:** se incorporó la
    **población municipal del DANE** (proyección/retroproyección 2005-2035; datos.gov.co no la publica a
    nivel nacional municipal, se usa el archivo oficial de `dane.gov.co` — ver
    [DATA_DICTIONARY](DATA_DICTIONARY.md#población-municipal--denominador-para-tasas-por-100000-habitantes-dane)) como
    features `log_poblacion`/`tasa_hist` —la **primera señal exógena** del modelo, pues las demás son
    autorregresivas— y el MAE multipaso cayó a ≈2,45 (ya batía a la línea base), a costa de algo de sMAPE. 
    - (b) **Objetivo en TASA por 100.000 habitantes:** modelar la
    incidencia por 100.000 habitantes (no el conteo crudo) iguala la escala entre Bogotá y un municipio pequeño;
    el pronóstico se **entrega en conteos** (se reconvierte con la población). Mejoró MAE **y** sMAPE frente a
    modelar conteos (multipaso 2,26 / 111,0). 
    - (c) **Nueva prueba de Poisson:** se volvió a probar `loss="poisson"` ahora
    con población — **vuelve a explotar** sobre conteos (MAE ~1e73 en la recursión, confirmando la Iteración
    3); la escala se resuelve con tasas, no cambiando la pérdida. 
    - (d) **Mezcla con persistencia (0,7):** modelar
    tasas amplifica el error en mega-ciudades (un error de tasa pequeño × población enorme = gran error de
    conteo → sobreestimación visible, p. ej. Bogotá/HOMICIDIO predecía 125 vs ~90 reales). Mezclar **0,7·modelo +
    0,3·persistencia** (calibrado por backtest) doma la sobreestimación **sin** perder la ventaja en volumen medio.
    *Resultado:* el modelo **iguala a la persistencia en MAE a 1 paso (≈1,95 vs 1,97 — diferencia ~1 %, dentro
    del ruido numérico entre ejecuciones; ver "Reproducibilidad")** y **la supera en MAE multipaso (≈2,20 vs
    2,57) y sMAPE multipaso (≈113,4 vs 114,7)**. En el desglose `por_volumen` gana en **MAE y sMAPE** en el
    tercil **medio** (MAE ≈0,83 vs 0,94); en el **alto** gana en sMAPE (≈71 vs 79) y queda en práctico empate
    en MAE (≈4,53 vs 4,50; la mezcla con persistencia doma la sobreestimación de las mega-ciudades); el de **volumen
    ínfimo** queda por detrás en ambas (≈0,48 vs 0,48: error absoluto diminuto, la persistencia es casi
    imbatible ahí). Bogotá/HOMICIDIO
    baja a ~115 (coherente con su tendencia al alza real). *(Valores ≈ porque el boosting fluctúa ~1 % entre
    ejecuciones; ver "Reproducibilidad" abajo. Los veredictos por tercil son estables.)* Cubierto con tests
    (`test_poblacion.py`, `test_forecasting.py`).
- **Iteración 9 (búsqueda de hiperparámetros con CV temporal):** se reemplazaron los hiperparámetros
    "elegidos a mano" por una **búsqueda sistemática**, con la salvedad metodológica clave: la puntuación usa el
    **walk-forward temporal** (sin fuga), **no `cross_val_score`/k-fold aleatorio** —que barajaría el tiempo y
    filtraría el futuro, dando métricas engañosamente buenas—. Se parametrizó `_new_estimator(overrides)` y se
    puntuaron **8 configuraciones** (variando learning-rate, profundidad, iteraciones, regularización y nº de
    hojas) por el **MAE multipaso de la predicción entregada** (modo tasa+mezcla, 2 orígenes), con la persistencia como referencia
    común. *Hallazgo:* las 8 configuraciones cayeron **dentro del 1,4 %** entre sí; la mejor alternativa
    (`learning_rate=0,03`, `max_iter=800`) mejoraba el MAE multipaso solo **−0,8 %** al validarla a 3 orígenes
    (2,215→2,197), **a costa de 2× el tiempo de entrenamiento** y con leve regresión a 1 paso → **no se adopta**.
    *Conclusión:* la búsqueda **confirma que los defaults ya eran un óptimo práctico** (no números mágicos), y
    deja la HPO (*Hyperparameter Optimization*) **reproducible** en el código (`_HGB_PARAMS` + `_new_estimator(overrides)` + `hgb_params` en el
    backtest). Resultado honesto y valioso para el rigor: el modelo está bien calibrado, no infra-ajustado.

- **Iteración 10 (champion vs challenger neuronal):** para decidir *con evidencia* si una red neuronal
    supera al gradient boosting —y no por moda—, se montó un **arnés de comparación** (`ml/vigia/ml/challenger.py`,
    CLI `vigia challenger`): mide un **challenger neuronal** —un MLP, `Pipeline(StandardScaler, MLPRegressor)`,
    en scikit-learn para conservar la huella ligera y la reproducibilidad (sin Torch/TF)— contra el HGB de
    producción bajo **exactamente el mismo** backtest walk-forward recursivo sin fuga (mismo filtro de series,
    mismo modo tasa/conteo, mismas features, mismos orígenes). Para reusar el backtest se generalizó
    `_walk_forward` con un parámetro `make_estimator` (su valor por defecto es el HGB de producción, así que el
    cambio **no altera** el modelo en producción ni la HPO (*Hyperparameter Optimization*) previa). El MLP exige escalado de features (a diferencia de
    los árboles), de ahí el `StandardScaler` en el pipeline. **El arnés solo EVALÚA**: no toca el artefacto
    en producción; cablear al ganador sería una decisión aparte y explícita. El veredicto y las métricas paralelas se
    regeneran de forma reproducible en `reports/challenger.json` (`champion` vs `challenger`, MAE/sMAPE a 1 paso
    y multipaso, con margen relativo). *Resultado sobre los datos reales (medición original: 2 orígenes, h=6):*
    el **champion HGB mantiene la ventaja** —MAE multipaso **2,276 vs 2,325** del MLP (**+2,2 %** a favor del
    HGB), y también gana a 1 paso y en sMAPE multipaso—. *Re-medido tras las Iteraciones 11-12* (filas
    repetidas conservadas, `media_hist` con ventana, 3 orígenes): el veredicto se sostiene y **la ventaja del HGB se
    amplía a +3,9 %** en MAE multipaso (**2,920 vs 3,034**; `reports/challenger.json` regenerado — el MAE del
    campeón calza exactamente con `model_report.json`), ganando también a 1 paso (2,545 vs 2,565) y en sMAPE
    multipaso (114,9 vs 115,7). *Conclusión:* **no se justifica
    cambiar de familia de modelo**; el gradient boosting es mejor Y más barato (el MLP tardó ~1,5 h de CPU vs
    minutos del HGB). Hallazgo honesto que cierra la pregunta "¿una red neuronal lo haría mejor?" con datos, no
    con intuición. Junto con la **simulación de escenarios** "¿y si…?"
    (`ml/vigia/ml/simulation.py`, endpoint `POST /simulate`) —una capa de escenarios hipotéticos sobre
    `predict` con palancas
    de intervención (supuesto del usuario) y de shock de población (palanca del modelo, vía tasa)—, esta
    iteración eleva la analítica de *predicción* a *prescripción explorable*, manteniendo la honestidad sobre lo
    que el modelo sí estima y lo que es un supuesto del usuario.

- **Iteración 11 (corrección del subconteo: silver deja de eliminar filas repetidas):** una auditoría interna
    detectó que el `drop_duplicates()` global de `build_silver` borraba **~3,77 millones de filas (~30 %)**:
    en las fuentes a grano de **evento** (`cantidad`≈1) dos hechos del mismo día y municipio con los mismos
    atributos son filas idénticas **legítimas** (el esquema publicado es estrecho), no duplicados del
    publicador. *Evidencia (triple, medida):* (a) las fuentes **pre-agregadas** por el publicador
    (`cantidad`>1) traen **0 filas repetidas** — la repetición solo existe donde el grano es evento; (b) la
    serie anual de homicidios **con las filas repetidas conservadas reproduce la cifra oficial** de la Policía
    (2003 ≈22,6 mil, 2023 ≈13,6 mil) y al eliminarlas quedaba un **15-30 % por debajo** (2003: 15,6 mil — imposible); (c) la
    paginación SODA2 es estable (`$order=:id`) y no reintroduce filas. *Impacto:* el universo pasa de ≈9,2 a
    **≈13,0 millones de hechos** (homicidios +21 %, capturas +66 %); las métricas del modelo se mueven a la
    nueva escala (MAE 1 paso ≈2,55 vs 2,60 persistencia, +1,6 %, dentro de la banda +1-3 %; multipaso
    **+15,6 %** y ahora gana también el **sMAPE multipaso a ambas líneas base**) y el **recall de la
    validación de anomalías salta de 7/11 a 10/11** — al eliminar las filas repetidas se perdían justamente los picos que los
    eventos documentados generan (Samaniego y la Brigada 30 pasan a detectarse). Se añadió un **test de
    regresión** (las filas idénticas se conservan) y el informe de calidad ganó el bloque **`procedencia`**
    (conciliación crudo→silver por fuente: descartes reales ≤0,06 %, solo fechas/códigos inválidos).

- **Iteración 12 (sobreestimación metropolitana: análisis de sensibilidad de la mezcla + ventana de `media_hist`):** la
    verificación territorial tras la Iteración 11 mostró que el pronóstico de HOMICIDIO en las grandes
    ciudades quedaba muy por encima del nivel reciente (Bogotá +59 %, Medellín +123 % sobre la media de los
    últimos 6 meses) aunque el agregado batiera a las líneas base. *Causa medida:* `media_hist` era una media
    **expansiva** de toda la historia; en series con caída secular (el homicidio de Medellín cayó ~90 % desde
    2003) esa "identidad" casi triplicaba el nivel actual (razón `media_hist/roll_mean_12` = **2,84**) y
    tiraba la predicción hacia arriba. *Experimento (sin tocar producción):* como la recursión del backtest
    realimenta la predicción **cruda** (la mezcla se aplica solo al servir), un único backtest con peso 1,0
    permite evaluar cualquier peso **a posteriori de forma exacta**; se midieron dos variantes × seis pesos
    (1,0→0,3). Hallazgos: (a) el **análisis de sensibilidad de `_BLEND_W`** confirma **0,7 como el peso elegido** y separa el
    mérito del modelo del de la persistencia embebida — sobre el modelo final, el análisis **versionado en
    [`reports/blend_sweep.json`](../reports/blend_sweep.json)** (regenerable con `make docker-blend-sweep`;
    con peso 0,7 reproduce `model_report.json` cifra por cifra, lo que valida el arnés) muestra que el
    **modelo puro** (peso 1,0) **pierde contra la persistencia a 1 paso** (MAE 2,716 vs 2,597, −4,6 %) pero
    **gana con holgura el horizonte multipaso** (+16,3 %); el MAE multipaso es casi plano entre 0,9 y 0,7
    (2,894-2,920, óptimo estricto en 0,9) y **se degrada de forma monótona por debajo** (hasta +9,0 % en
    0,3), mientras que bajar el peso sigue mejorando el 1 paso (máximo +4,6 % en 0,4) a costa del horizonte
    entregado → **0,7 es el mayor peso de modelo que gana con claridad en ambos frentes** (+2,0 % a 1 paso,
    +16,1 % multipaso). Además, la mezcla sola **no** corrige la sobreestimación (con 0,7 Medellín
    seguía en +123 %); (b) **`media_hist` con ventana de 60 meses** (`min_periods=1`: una serie más corta que
    la ventana conserva exactamente su media expansiva — solo se adaptan las largas con deriva secular)
    elimina el tirón en la propia feature (razón de Medellín 2,84 → **1,08**) y, con el mismo peso 0,7,
    **domina a la variante expansiva en todo el agregado**: MAE 1 paso 2,545 vs 2,554 (skill **+2,0 %**), MAE
    multipaso 2,920 vs 2,934 (**+16,1 %**), MASE 1,347/1,471, y el **tercil alto pasa a ganar** (6,23 vs
    6,25; MASE 1,006, el mejor) — a cambio de ~0,4 pt de sMAPE multipaso (114,9, aún por delante de ambas
    líneas base). El desvío metropolitano cae a la mitad o más: Bogotá +59 → +42 %, Medellín +123 → **+48 %**,
    Cali +20 → **+5 %**. *Se cablea la ventana* (constante `HIST_WINDOW` en `features.py`, con un test que
    fija que una época alta fuera de la ventana ya no contamina la media) y **se conserva 0,7** — el análisis
    queda documentado y reproducible. *Límite declarado:* el sobrenivel metropolitano no desaparece del todo
    (Bogotá ≈+42 % sobre la media reciente; parte es estacionalidad legítima —los primeros meses del año son
    más bajos— y parte, el costo de un modelo global); se declara en vez de ocultarse.

- **Iteración 13 (punto ciego MAD=0 del detector de anomalías: respaldo de escala calibrado):** un test
    intermitente del CI destapó que el z robusto dejaba **sordas** a las series quietas: con >50 % de
    residuos idénticos (típico de municipios pequeños con muchos ceros) la MAD del grupo es 0 y el z quedaba
    forzado a 0 → ningún pico alertaba, por extremo que fuera. *Prevalencia medida:* **79 % de las 13.431
    series** del panel. *Experimento (tres variantes sobre el panel real):* el detector vigente reproduce las
    22.867 alertas versionadas; un respaldo **ingenuo** (media de desviaciones absolutas como escala) las
    **triplica** (71.784) con **91 % del exceso en blips de ≤3 hechos** — descartado; un respaldo **calibrado**
    (misma escala con **piso de 1,0 hecho**: solo alerta lo que supera `z_threshold`×piso ≈ 3,5 hechos sobre
    la mediana móvil) añade **7.445 alertas con cero ruido de ≤3 hechos** (mediana 5 hechos) y solo mueve 69
    alertas previas (re-umbral del bosque global). Entre lo destapado: **El Tambo 2025-09 (75 secuestros
    extorsivos en un mes)**, Ipiales 2016-08 (88 casos de trata) y Medellín 2009-06 (71 de trata). *Se
    cablea* (`anomaly._z_robusto`, la ruta MAD>0 queda intacta; 2 tests de regresión: pico en serie quieta →
    alerta, blip 0→2 → silencio) y *se re-mide todo:* el benchmark sintético sigue verde (precisión ≥0,85 /
    recall ≥0,9), el catálogo pasa a **30.243** alertas (tasa 1,13 % de los meses-serie, ≈2 por serie), la
    corroboración interna **sube** de 23,3 % a **24,6 %** (7.433 respaldadas) y el recall contra eventos
    documentados pasa de 10/11 a **11/11** — el fallo que se cierra es justamente **Toribío 2011**, cuya
    serie de TERRORISMO, con la mayoría de los meses en cero, caía en el punto ciego (el diagnóstico
    anterior, «línea base alta», era incorrecto: era MAD=0).

**Estado actual:** modelo aceptado y **reforzado**: tras las Iteraciones 8-12 **supera a la persistencia en
MAE 1 paso y multipaso y en sMAPE multipaso** (`supera_linea_base_mae = true`,
`supera_linea_base_smape_multipaso = true`). **A 1 paso mantiene una ventaja modesta en MAE** (≈2,55 vs 2,60
en la ejecución vigente, +2,0 %; la ventaja fluctúa **entre ≈+1 y ≈+3 % según la ejecución** — al ser una
diferencia pequeña entre errores casi iguales, el ruido multihilo ~1 % del MAE se amplifica a puntos
porcentuales del margen) **y cede en sMAPE** (la persistencia
es casi imbatible en error relativo a un mes sobre conteos ínfimos), pero ese no es el horizonte que se
entrega. El desglose `por_volumen` muestra que el modelo gana en MAE y sMAPE en los terciles
**medio** y **alto** (en el alto, MAE por margen fino —≈6,23 vs 6,25— y sMAPE con holgura —≈75 vs 83—, con el
mejor MASE, ≈1,01); el de **volumen ínfimo** queda por detrás en ambas (error absoluto diminuto, "repetir el último
valor" es casi imbatible ahí). El aporte del modelo es
la **proyección del horizonte completo** con tasas comparables entre territorios. **Las métricas
vigentes — sMAPE/MAE
del modelo y de la línea base, nº de series, anomalías — se regeneran en cada ejecución del pipeline y
quedan en [`reports/model_report.json`](../reports/model_report.json) y
[`reports/silver_quality.json`](../reports/silver_quality.json) (las cifras que prevalecen, auditables).** La
tabla siguiente es una ejecución de referencia (no sustituye al artefacto regenerado):

Ejecución de referencia (16 datasets, backtest **walk-forward**; regenerada por `make deploy`, ver
`reports/model_report.json`): **13.089 series** modeladas, 1.106 municipios, 20 categorías, **12,98 millones**
de hechos modelados, periodo 2003-01 → 2026-05, **30.243 anomalías** (11.888 alta / 18.355 media). Tras la
Iteración 6 el reporte añade `por_volumen` (terciles), `multipaso` (agregado + `por_paso`) y
`pi_cobertura_empirica_pct`.

> **Conteo de municipios (silver vs. modelado).** `silver_quality.json` reporta **1.126** municipios
> (todos los que aparecen en algún hecho de silver), mientras `model_report.json` reporta **1.106**
> `municipios_modelados`: la diferencia (20) son municipios cuyas series no alcanzan el umbral de actividad
> (`min_nonzero`, ≥12 meses no nulos) y quedan fuera del **modelado** —no del tablero ni del panorama, que
> usan todo silver—. Sobre la completitud: `silver_quality.json` da `completitud_pct` 100 % **por
> construcción** (silver imputa el marcador `NO REPORTADO` en vez de dejar nulos); el campo
> `placeholders_pct` expone el **% real de no reportados** por columna sin maquillarlo (en la ejecución de
> referencia: `zona` ≈87 %, `arma_medio` ≈82 %, `grupo_etario` ≈43 %, `sexo` ≈34 %; ver [2](#2-ingeniería-de-datos-preparación)).
>
> **Conteo de series (por qué difiere entre arneses).** El nº de series no es único porque cada arnés
> aplica su propio filtro de historia mínima: el **modelado** reporta **13.089** series
> (`model_report.json`), la **detección/evaluación de anomalías** opera sobre un universo algo mayor (no
> exige el mismo umbral de meses no nulos), y el **arnés champion/challenger** (Iteración 10) puntúa
> las series bajo su propio criterio (el conteo de cada ejecución queda en su registro; el reporte
> versionado publica métricas y configuración). Son universos distintos por diseño, no cifras
> contradictorias.

| Iteración | Datos | Backtest | sMAPE modelo | sMAPE base | MAE modelo | MAE base |
|---|---|---|---|---|---|---|
| Iter 1 | muestra 8.000 (sesgada) | holdout | 185,4 | 164,7 | 2,63 | 2,42 |
| Iter 2 | 8 datasets completos (pérdida cuadrática) | holdout | 96,95 | 111,05 | 2,64 | **2,38** |
| Iter 3 | 8 datasets (poisson, revertida) ❌ | holdout | 103,4 | 111,0 | 3,4e5 ❌ | 2,38 |
| Iter 5-7 · 1 paso | 16 ds, conteos | walk-forward rec. (3) | 119,33 | **117,87** | 4,13 | **1,97** |
| Iter 5-7 · multipaso h6 | 16 ds, conteos | walk-forward rec. (3) | **102,80** | 114,69 | 5,02 | **2,57** |
| Iter 8 · 1 paso | 16 ds + población, **tasa+mezcla** (aún borraba filas repetidas; superada) | walk-forward rec. (3) | ≈126 | **117,9** | **≈1,95** | 1,97 |
| Iter 8 · multipaso h6 | 16 ds + población, **tasa+mezcla** (aún borraba filas repetidas; superada) | walk-forward rec. (3) | **≈113,4** | 114,7 | **≈2,20** | 2,57 |
| **actual (Iter 11-12) · 1 paso** | 16 ds + población, tasa+mezcla, **filas repetidas conservadas**, `media_hist` 60 m | walk-forward rec. (3) | ≈127 | **120,1** | **≈2,55** | 2,60 |
| **actual (Iter 11-12) · multipaso h6** | 16 ds + población, tasa+mezcla, **filas repetidas conservadas**, `media_hist` 60 m | walk-forward rec. (3) | **≈114,9** | 116,9 | **≈2,92** | 3,48 |

(Cifras de la ejecución de referencia regenerada por `make deploy` — ver `reports/model_report.json`. Tras las
**Iteraciones 11-12** (se dejó de eliminar filas repetidas —escala corregida, +41 % de hechos— y `media_hist` con ventana
de 60 meses): el modelo **queda por delante de
la línea base en MAE a 1 paso** (≈2,55 vs 2,60; margen de **+1 a +3 % según la ejecución**, que el ruido ~1 %
mueve en puntos porcentuales) **y la bate en MAE y sMAPE multipaso** (filas "actual"); **a 1 paso aún cede en
sMAPE** (persistencia casi imbatible en error relativo a un mes). Las filas "Iter 5-7" e "Iter 8" preservan
los estados previos — conteos crudos y datos aún sin las filas repetidas, respectivamente; sus MAE no son comparables
con los actuales porque la escala del dato cambió — el contraste evidencia cada salto.)

El desglose `por_volumen` que el reporte
**regenera**:
- **`por_volumen`** (terciles): el modelo gana en **MAE y sMAPE** en los terciles **medio**
  (MAE ≈0,90 vs 1,03) y **alto** (MAE por margen fino, ≈6,23 vs 6,25 — las urbanas de alto volumen, domadas
  por la mezcla con persistencia y la ventana de `media_hist` —, sMAPE con holgura, ≈75 vs 83, y el mejor
  MASE, ≈1,01). El de **volumen ínfimo** queda por
  detrás en ambas (≈0,51 vs 0,51; error absoluto diminuto, "repetir el último valor" es casi imbatible ahí). El
  flag `gana_modelo` por tercil lo registra (el medio gana de forma estable; el margen del alto es fino y
  puede oscilar entre ejecuciones por la fluctuación de ~1 %).
- **`multipaso`** (horizonte recursivo de 6 meses, lo que se entrega): contra la **persistencia multipaso**
  el modelo gana **tanto en MAE (≈2,92 vs 3,48) como en sMAPE (≈114,9 vs 116,9)**, con ventaja **creciente**
  por paso, porque la persistencia se degrada rápido con el horizonte (a 1 paso el modelo aún cede en sMAPE;
  la ventaja se abre al proyectar). Contra la **estacional multipaso** gana en MAE (≈2,92 vs 3,20) y
  ligeramente en sMAPE (≈114,9 vs 115,5), pero la ventaja en MAE **no es monótona por paso** (a 2-3
  meses la estacional queda por delante: 2,89 vs 3,07 en el paso 2). Se reporta además la **cobertura empírica** de la banda: **80,0 %**, igual
  al 80 % nominal tras la **calibración conformal** de `pi_scale` (antes 94,4 %; ver [4](#4-evaluación-del-modelo)).

> Mejora futura para series de gran volumen: modelos por nivel de volumen o LightGBM/Prophet; pérdida de
> Poisson con techo de predicción robusto.

## 5. Despliegue

- Servicio de inferencia FastAPI (`api/`) empaquetado en Docker.
- Orquestación completa vía `docker-compose` (datos, IA, backend, frontend).
- Configuración por variables de entorno (`.env`).

## 6. Monitoreo y mantenimiento

> Una vez desplegado, el sistema se vigila solo con un **semáforo** (verde/amarillo/rojo):
> avisa si los datos dejan de llegar (frescura), si cambian de forma respecto a lo normal (deriva) o si el
> pronóstico empieza a fallar (backtest), para saber cuándo conviene reentrenar.

CRISP-ML(Q) se distingue de CRISP-DM precisamente por esta fase. El monitoreo se **diseña sobre señales que
el pipeline ya emite** (`reports/model_report.json` y `reports/silver_quality.json`, regenerados en cada
ejecución), de modo que no requiere instrumentación nueva para empezar a operar.

**Monitoreo ya está implementado** (`ml/vigia/ml/monitoring.py`, CLI `vigia health`, endpoint
`GET /monitoring` y la pestaña **Salud del modelo** del tablero): un reporte reproducible
(`reports/model_health.json`) con **semáforo** (verde/amarillo/rojo) sobre cuatro señales operativas —
**frescura** de datos (rezago en meses **más el desglose por categoría ≈ fuente**: las que van más de 6
meses detrás del panel se listan como *estancadas* y elevan la señal a amarillo — con solo el máximo
global, una fuente detenida quedaba invisible mientras otra siguiera fresca), **deriva** vía **PSI**
(Population Stability Index, umbrales
estándar 0,1/0,25, sobre los conteos de delito recientes vs. una **ventana rolling** de los ~18 meses previos
—no toda la historia, que por el crecimiento secular de 20 años dejaría la deriva siempre en rojo—),
**cobertura del denominador poblacional** (sin la población DANE el modelo degrada a conteos; antes ocurría
en silencio, ahora la señal lo declara) y un **backtest extendido a 12
meses** que valida el horizonte largo (el que el entrenamiento a 6 no cubre) con el mismo walk-forward sin
fuga—. El estado global es el peor de las señales. El backtest a 12 meses es costoso (recalcula features por
paso sobre todo el panel), por eso es un comando **offline** y la API solo entrega el JSON ya escrito.

### 6.1 Deriva de datos (entrada)
Comparar `silver_quality.json` entre ejecuciones consecutivas. **Señales y umbrales de revisión:**
- **Volumen por fuente** (`fuentes`): variación relativa **> ±20 %** mes a mes → ¿la fuente dejó de
  actualizarse en SODA2 o cambió de esquema? (riesgo real: la API de datos.gov.co puede cambiar columnas).
- **Subregistro** (`placeholders_pct`): aumento **> +5 pp** en un campo → degradación de calidad de la fuente.
- **Cobertura** (`municipios_unicos`, `categorias`, `rango_fechas`): caídas o estancamiento de la fecha
  máxima → la fuente no trae el mes nuevo.
- **Linaje por fuente** (`procedencia`): además de la conciliación crudo→silver, cada fuente lleva su
  **fecha de ingesta** (`fecha_ingesta`, elevada desde el meta del bronze — que no se versiona — al reporte
  versionado): la procedencia del dato es auditable desde el repo sin correr el pipeline.
- **Alertas estructurales** (`alertas`): cualquier entrada no vacía (nulos, cantidades ≤0, fechas futuras)
  detiene la promoción a gold.

### 6.2 Deriva de concepto / degradación del modelo
Comparar `metricas_backtest` entre ejecuciones. **Disparadores de alerta:**
- El modelo **deja de superar a la persistencia**: `supera_linea_base_smape_multipaso = false` → revisar.
- **sMAPE** (1-paso o multipaso) empeora **> 10 % relativo** respecto a la ejecución previa.
- **Cobertura empírica de la banda** (`pi_cobertura_empirica_pct`) sale del rango **[70 %, 90 %]** (nominal
  80 %) → recalibrar la dispersión / la incertidumbre está mal dimensionada.
- **Estabilidad de interpretabilidad** (`interpretabilidad.features`): si `media_hist`/`roll_mean_12` dejan de
  dominar el top, hubo un cambio estructural en las series → investigar antes de confiar en el pronóstico.
- **Volumen de anomalías** (`anomalias.total` y tasa por serie): un salto desproporcionado señala cambio de
  régimen o problema de datos (ligado a la calibración de [3](#3-ingeniería-del-modelo), `anomaly.py`).

### 6.3 Versionado de modelos y trazabilidad
- Cada artefacto serializado (`models/forecaster.joblib`) lleva su **metadata de entrenamiento**
  autoidentificable: `trained_at`, `seed`, `feature_cols`, `metrics` e `importancias`. `model_report.json`
  es el **registro auditable por ejecución**.
- *Recomendado:* archivar el reporte con marca temporal (`reports/history/model_report_<trained_at>.json`)
  para comparación longitudinal y **rollback** (conservar el `.joblib` anterior si una ejecución degrada).

### 6.4 Política de reentrenamiento
- **Programado:** mensual, al publicarse el nuevo mes en SODA2 (`make docker-pipeline`). Pipeline
  **re-ejecutable** y reproducible (semilla fija).
- **Disparado:** si (Sección [6.1](#61-deriva-de-datos-entrada)/[6.2](#62-deriva-de-concepto--degradación-del-modelo)) superan umbral.
- **Post-reentrenamiento:** invalidar la **caché de IA en Redis** (pronóstico guardado en caché por TTL; forzar con
  `?nocache=1`, privilegio del rol admin) para no entregar proyecciones del modelo anterior.

### 6.5 Monitoreo de servicio (SLOs)
- **Implementado:** `/health` (estado de la BD gold), *logs* estructurados, cabecera `X-Cache` (HIT/MISS),
  *rate-limiting* y *timeouts* alineados (~240s) por la latencia del LLM local en CPU (~30–90s/respuesta).
  **Healthchecks de contenedor en los 6 servicios** (db/redis/ollama/ml/backend/frontend) con `depends_on:
  service_healthy` encadenado, de modo que `make up` (`--wait`) solo retorna cuando la plataforma responde de
  verdad (el backend distroless se autoconsulta vía subcomando `/api healthcheck`).

### 6.6 Runbook mensual (operación mínima sin automatización)
Tras cada ejecución: 
1. revisar `silver_quality.json` ([6.1](#61-deriva-de-datos-entrada)); 
2. comparar `model_report.json` con el anterior ([6.2](#62-deriva-de-concepto--degradación-del-modelo))
3. si todo está dentro de umbrales, promover; si no, aplicar la acción documentada
(reentrenar, recalibrar banda/anomalías, o reportar cambio de esquema de la fuente). 
4. refrescar el reporte de salud con **`make docker-health`**, que regenera `reports/model_health.json` (frescura, deriva PSI y backtest a 12 meses) y alimenta la pestaña *Salud del modelo*. Es **offline a
propósito** —no va en el pipeline ni en `make deploy`— porque el backtest largo tarda minutos.

## Ética y uso responsable

VigIA es una herramienta de **apoyo a la decisión a nivel territorial agregado**, no un sistema de
vigilancia ni de policía predictiva (*predictive policing*) sobre individuos. Consideraciones:

- **Solo datos agregados y públicos.** No se procesa información personal identificable.
- **Atributos demográficos, solo para medir el subregistro.** Las fuentes traen `sexo`, `genero`,
  `grupo_etario` y `zona`, pero VigIA **no** los usa para desglosar la incidencia ni como variables del
  modelo: se conservan únicamente para cuantificar el subregistro (`placeholders_pct`; p. ej. `sexo` ≈34 %,
  `grupo_etario` ≈43 % de «NO REPORTADO»). Desglosar el delito por grupo demográfico —pudiendo hacerlo—
  señalaría poblaciones y contradiría el principio de agregación y no-perfilamiento; se excluye por diseño.
- **Sesgo de los datos.** Reflejan registros oficiales (denuncias/capturas), sujetos a subregistro y a
  sesgos de despliegue policial. Las predicciones **no** deben interpretarse como criminalidad "real"
  ni usarse para estigmatizar territorios o poblaciones.
- **Transparencia.** El asistente cita siempre la fuente; el código y los datos son abiertos y auditables.

### El bucle de retroalimentación de la policía predictiva (y cómo se acota)

El riesgo central de cualquier analítica predictiva de criminalidad es un **bucle de retroalimentación**:
más patrullaje en un territorio → más hechos *registrados* allí → mayor incidencia proyectada → más
patrullaje, concentrando el esfuerzo (y el estigma) en las mismas zonas con independencia del delito real.
VigIA **no puede corregir este sesgo de raíz con dato abierto** (el portal no publica una variable de
*exposición*/despliegue policial por municipio-mes que permita "descontarlo") — y lo declara como límite en
vez de simularlo. Lo que sí hace es **acotar el riesgo por diseño**:

- **Granularidad territorial agregada (no individual).** El sistema opera a `municipio × categoría × mes`;
  no perfila personas, no desciende a barrio/cuadrante ni desglosa la incidencia por atributos de la víctima
  (sexo/edad) —aunque las fuentes lo permitirían— (ver acotación en [IMPACTO.md](IMPACTO.md)). No hay PII.
- **Anomalías relativas a cada serie, no al volumen absoluto.** El detector normaliza por la propia historia
  de cada municipio (`anomaly.py`), de modo que las alertas **no se concentran mecánicamente en las
  ciudades grandes/pobres** de mayor conteo; un repunte vale por su atipicidad local, no por su tamaño.
- **Las "respuestas" no son alertas.** Capturas/incautaciones/recuperaciones se excluyen de las alertas
  (`RESPONSE_CATEGORIES`): un alza de actividad policial **no** dispara una "alerta de inseguridad" que
  pida más policía → se rompe un eslabón del bucle.
- **Aviso en el punto de uso.** La pestaña **Alertas tempranas** advierte explícitamente que las anomalías son
  relativas a cada territorio, reflejan hechos registrados (pueden seguir el despliegue) y **no deben usarse
  para estigmatizar territorios ni vigilar personas**; el asistente lleva la misma cláusula de **uso
  responsable** en su *system prompt* (`rag/pipeline.py`) y reencuadra peticiones de perfilamiento individual.
- **El humano decide, no el modelo.** VigIA prioriza *qué* delito y *qué* municipio; el detalle operativo y
  la decisión de despliegue quedan en el equipo local. El sistema **informa, no automatiza** el despliegue.

**Lo que NO resuelve (honestidad):** ninguna de estas medidas elimina el sesgo de subregistro/despliegue
subyacente a los datos. Por eso las cifras se comunican siempre como *hechos registrados* y el uso recomendado
es la **comparación observado-vs-proyectado** para evaluar intervenciones, no la atribución de "peligrosidad"
a un territorio o una población.
