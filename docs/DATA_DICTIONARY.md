# Diccionario de datos

> Este documento es la referencia técnica de los datos de VigIA: de dónde sale cada fuente,
> cómo se llama cada campo y cómo se unifican conjuntos con formatos distintos en un solo modelo. Para el
> panorama general y el impacto, ver el [README](../README.md).

## Fuentes (datos.gov.co — catálogo *Seguridad y Defensa*, Policía Nacional)

Consumidas vía API SODA2: `https://www.datos.gov.co/resource/<id>.json`.

Esquemas **verificados** contra la API SODA2. **20 conjuntos de datos.gov.co en total**: 16 datasets de
eventos + 2 administrativos (todos de la **Policía**), la referencia oficial **DIVIPOLA** (DANE, abajo) y
una fuente de **otra entidad** —la **Fiscalía General de la Nación**— como capa paralela de **Justicia**
(ver [Capa "Justicia"](#capa-justicia--fiscalía-general-de-la-nación-fuente-de-otra-entidad-capa-paralela)).
La **población municipal DANE** es una referencia demográfica adicional de `dane.gov.co` —no de
datos.gov.co— y **no entra en ese conteo de 20** (ver
[Población municipal](#población-municipal--denominador-para-tasas-por-100000-habitantes-dane)). Los 20 se publican
bajo licencia **CC BY-SA 4.0**, verificada dataset a dataset contra la API de metadatos del portal
(2026-07-06; comando reproducible y fecha de última actualización por fuente en
[DATASETS.md](DATASETS.md#licencia-y-vigencia-de-las-fuentes)). Las **filas** son
volúmenes crudos aproximados de la API;
los conteos definitivos tras limpieza viven en [`reports/silver_quality.json`](../reports/silver_quality.json),
regenerado en cada ejecución. Ese informe distingue `completitud_pct` (100 % por construcción: silver imputa el
marcador `NO REPORTADO` en vez de dejar nulos) de `placeholders_pct` (el **% real de no reportados** por
campo). La **alineación de estas fuentes con la Hoja de Ruta Nacional de Datos Abiertos
Estratégicos** se documenta y verifica en la sección
[Alineación con la Hoja de Ruta](#alineación-con-la-hoja-de-ruta-nacional-de-datos-abiertos-estratégicos-2025-2026).

| id dataset | SODA id | Familia | Fecha | Filas (aprox.) | Notas |
|---|---|---|---|---|---|
| `homicidios` | `m8fd-ahd9` | A | ISO | 339.653 | `arma_medio`, `_modalidad_presunta` |
| `hurto_vehiculos` | `csb4-y6v2` | A | ISO | 382.563 | `tipo_delito` (categoría por artículo) |
| `hurto_personas` | `4rxi-8m8d` | A | ISO | 641.724 | delito urbano más frecuente (por hechos —`cantidad`—, no por filas) |
| `hurto_residencias` | `7mn7-vzqp` | A | ISO | 609.597 | — |
| `delitos_sexuales` | `bz43-8ahq` | A | ISO | 438.526 | `sexo`, `zona` (desagregable por género) |
| `delitos_informaticos` | `4v6r-wu98` | A | ISO | 491.867 | `descripcion_conducta` (no mapeada) |
| `extorsion` | `q2ib-t9am` | A | ISO | 127.521 | — |
| `secuestro` | `d7zw-hpf4` | A | ISO | 10.267 | `tipo_delito` (extorsivo/simple) |
| `terrorismo` | `yi5j-5fe9` | A | ISO | 15.337 | `zona` |
| `trata_personas` | `95c7-mm6s` | A | ISO | 5.048 | `descripcion_conducta` (no mapeada) |
| `violencia_intrafamiliar` | `vuyt-mqpw` | B | dd/mm/yyyy | 682.558 | `genero`, `grupo_etario` |
| `amenazas` | `meew-mguv` | B | dd/mm/yyyy | 650.347 | `genero`, `grupo_etario` |
| `reporte_capturas` | `3jdh-nmwu` | B | dd/mm/yyyy | 3.673.572 | `descripcion_conducta_captura` (respuesta) |
| `incautacion_armas` | `2iz5-9bbz` | B | dd/mm/yyyy | 421.224 | usa `municipio_hecho`; `clase_bien` (respuesta) |
| `recuperacion_vehiculos` | `dhy3-732k` | B | dd/mm/yyyy | 276.743 | `clase_bien` (respuesta) |
| `hurto_modalidades` | `d4fr-sbn2` | B | dd/mm/yyyy | 44.169 | categoría en `tipo_de_hurto`; `genero`, `grupo_etario` |
| `auditorias` | `yiu6-gjbe` | admin | — | 953 | no es serie delictiva |
| `demandas_notificadas` | `4uxk-dt6c` | admin | — | 18.074 | no es serie delictiva |

> ⚠️ **Correcciones de integración:** `reporte_capturas`, `incautacion_armas` y `recuperacion_vehiculos`
> resultaron ser **familia B** (no A como sugería el inventario inicial). `mineria_ilicita` (`4y5w-y5sj`)
> se **excluyó**: su estructura (`fecha_de_hecho`, sin `codigo_dane` ni `cantidad`) no encaja en la serie
> delictiva. `hurto_modalidades` (`d4fr-sbn2`): el *profiling* inicial estaba generado con el SODA id
> equivocado (mostraba datos de vehículos); **verificado contra la API es familia B**, con la categoría en
> la columna `tipo_de_hurto` y **3 modalidades NO vehiculares** — HURTO ABIGEATO (≈37.500), PIRATERÍA
> TERRESTRE (≈4.800) y ENTIDADES FINANCIERAS (≈1.800). **No solapa** con `hurto_vehiculos` (automotores /
> motocicletas), por lo que se integra a la serie sin doble conteo (verificado: el conteo de vehículos no
> cambió al añadirla).
>
> Inventario completo de URLs en [../docs/DATASETS.md](../docs/DATASETS.md).

### Expansión desde el *Asset Inventory* (catálogo `uzcf-b9dh`)

El catálogo se amplió consultando el **Asset Inventory** oficial de la categoría *Seguridad y Defensa*
(`uzcf-b9dh`, ~169 datasets publicados/públicos/aprobados). Tras una selección crítica (relevancia para el
reto de **Seguridad Ciudadana**, compatibilidad de esquema, cobertura, frescura y NO duplicación), se
añadieron **8 fuentes de la familia A "mensual"** de la Policía Nacional —mismo esquema que `homicidios`
(`cod_muni` 5 díg., `fecha_hecho` ISO, `cantidad`), cobertura **nacional**, actualización **mensual** y
datos vigentes a **2026-05**—: `hurto_personas`, `hurto_residencias`, `delitos_sexuales`,
`delitos_informaticos`, `extorsion`, `secuestro`, `terrorismo` y `trata_personas`. Son de **incorporación directa**: no
requieren cambios en `silver.py` (verificado end-to-end). Cubren los delitos de mayor preocupación
ciudadana que faltaban (el hurto a personas es el delito urbano más frecuente del país).

**Fuentes evaluadas y descartadas (con justificación — rigor de selección):**
> - *Incautación de Estupefacientes* (`kk69-w2jj`) y demás incautaciones de droga: `cantidad` en
>   **unidades mixtas** por `clase_bien` (kg de marihuana vs g de cocaína vs unidades) → no son sumables;
>   además son *respuesta*, no delito.
> - *Lesiones Personales* (`72sg-cybi`) / *Lesiones en accidente de tránsito* (`ntej-qq7v`): **mezclan**
>   lesión intencional (riña) con accidente de tránsito → distorsionarían la señal de violencia sin una
>   clasificación fila a fila (el componente vial pertenece a *movilidad*, no al reto).
> - *Hurto abigeato* (`p88b-5ac7`), *piratería terrestre* (`sutf-7dyz`), *entidades financieras*
>   (`i7h7-wmjc`): **ya contenidos** en `hurto_modalidades` (`d4fr-sbn2`) → doble conteo.
> - Versiones **duplicadas en otra periodicidad** (p. ej. *Violencia intrafamiliar* mensual `gepp-dxcs`,
>   *Terrorismo* trimestral `37p5-impc`, *Delitos sexuales* trimestral `fpe5-yrmw`) → se elige una sola
>   versión por delito.
> - El resto del inventario es **no delictivo** (índices de información clasificada, directorios de
>   oficinas, esquemas de publicación, cuadrantes, subsidios de vivienda militar, hospital militar…).

## Alineación con la Hoja de Ruta Nacional de Datos Abiertos Estratégicos 2025-2026

Las fuentes no se eligieron solo por disponibilidad: priorizan el conjunto que la **Hoja de Ruta Nacional
de Datos Abiertos Estratégicos 2025-2026** marca como estratégico para el reto. Verificado contra la API
(`https://www.datos.gov.co/resource/fn2v-r4gu.json`):

| Campo (registro de la Hoja de Ruta) | Valor |
|---|---|
| SODA id (Hoja de Ruta) | `fn2v-r4gu` |
| Categoría / id de registro | **DEFENSA** / **id 70** |
| Conjunto priorizado | *"Seguridad y justicia – Estadísticas de criminalidad"* |
| Entidad responsable | Ministerio de Defensa |
| Sistema de información | Observatorio de Derechos Humanos y Defensa Nacional |
| Criterio de priorización | *Our Data Index 2025* |
| Estado | APERTURADO |

**VigIA ejecuta la recomendación de la Hoja de Ruta.** El registro id 70 enlaza nominalmente 4 datasets y
recomienda *consolidar todos los delitos*; la capa `silver.py` consolida las 16 fuentes de eventos (13 de
delito + 3 de respuesta institucional) en un modelo único; las **13 de delito** materializan la
recomendación. Mapeo verificado dataset↔Hoja de Ruta:

| Fuente VigIA | SODA2 | En la Hoja de Ruta (id 70) |
|---|---|---|
| `homicidios` | `m8fd-ahd9` | ✅ Enlazada nominalmente |
| `hurto_residencias` | `7mn7-vzqp` | ✅ Enlazada nominalmente |
| `delitos_informaticos` | `4v6r-wu98` | ✅ Enlazada nominalmente |
| `delitos_sexuales` | `bz43-8ahq` | ✅ Enlazada nominalmente |
| Las otras 12 fuentes del catálogo (9 de delito + 3 de respuesta) | (ver tabla de Fuentes, arriba) | ◐ Mismo conjunto priorizado *"Estadísticas de criminalidad"*; las de delito materializan la recomendación de consolidar |

**Conjunto priorizado aún no aperturado — aporte de VigIA.** La Hoja de Ruta prioriza además *"Seguridad y
justicia – Violencia basada en género"* (registro **id 39**, categoría ESTADÍSTICAS, entidad DPS), con
estado **NO APERTURADO** y recomendación **APERTURAR**. VigIA aporta señal proxy sobre ese vacío mediante
`delitos_sexuales` (desagregable por `sexo`/`zona`) y `violencia_intrafamiliar` (con `genero`/`grupo_etario`).

> **Acotación del eje "Justicia".** En la Hoja de Ruta, la categoría *JUSTICIA Y DEL DERECHO* (id 137) se
> refiere al registro público de propiedad/tenencia de tierras (Superintendencia de Notariado y Registro),
> no a criminalidad. El núcleo de incidencia delictiva vive en **DEFENSA, id 70** (Policía). VigIA además
> aporta una señal **propiamente de Justicia** con una fuente de **otra entidad**, la **Fiscalía General de la
> Nación**: judicialización (ver [Capa "Justicia"](#capa-justicia--fiscalía-general-de-la-nación-fuente-de-otra-entidad-capa-paralela)),
> que mide qué fracción de las noticias criminales avanza en la cadena penal — el complemento natural al
> conteo de delitos para "Seguridad y Justicia".

Verificación reproducible (consulta usada):

```bash
# Registro priorizado de criminalidad (DEFENSA, id 70)
curl "https://www.datos.gov.co/resource/fn2v-r4gu.json?\$where=categoria='DEFENSA'&\$select=id,conjunto_datos_priorizados,enlace_portal_dato_abierto,recomendaciones,observaciones"
```

## Capa "Justicia" — Fiscalía General de la Nación (fuente de OTRA entidad, capa paralela)

Las 16 fuentes de eventos anteriores (13 de delito + 3 de respuesta institucional) son **todas de la Policía
Nacional**: miden el *hecho registrado*. Para cubrir el otro eje del reto —**Justicia**— y romper la
dependencia de una sola entidad, VigIA incorpora un **dataset abierto de la Fiscalía General de la
Nación** (*entidad distinta*; el 20.º del conteo total, tras los 16 de eventos, los 2 administrativos y
DIVIPOLA), que aporta una dimensión
que ningún conteo de delitos tiene: la **JUDICIALIZACIÓN** (qué fracción de las noticias criminales
avanza más allá de la indagación).

| Campo | Valor |
|---|---|
| Dataset | *Procesos Fiscalía — V3* (`dbdv-iihs`, público; la V2 es privada → 403) |
| Entidad | **Fiscalía General de la Nación** (no la Policía) |
| Volumen | **~23 millones** de procesos (micro-dato anonimizado, 1 fila por proceso) |
| Grano materializado | `municipio × año × etapa` |
| Dimensión diferencial | `etapa`: **Indagación → Investigación → Juicio → Ejecución de Penas** |
| Cobertura | **1.126 municipios**, **2004-2026** (SPOA arranca con la Ley 906 de 2004) |

**Por qué es una capa PARALELA (no se fusiona con la serie de la Policía).** Una *noticia criminal / proceso*
de la Fiscalía **no** es un *hecho registrado* por la Policía; sumarlas sería **doble conteo**. Por eso no
entra a `silver.py` ni al `CATALOG` de delitos: vive aparte, en `gold/justicia_anual.parquet`,
`gold/justicia_resumen.parquet` y `reports/justicia.json`. Su valor es la `etapa`, ausente en cualquier serie
de incidencia.


- **Esquema bronze** (`data/bronze/justicia_procesos.parquet`, ya agregado por el streaming):

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_dane_hecho` | str | Código DANE del municipio del hecho (5 díg.; se cruza con DIVIPOLA) |
| `a_o_hecho` | str | Año del hecho |
| `etapa` | str | Etapa procesal (texto crudo de la Fiscalía) |
| `n_procesos` | int | Conteo de procesos del grupo (agregado localmente) |

- **Gold** (`etl/justicia.py`): `justicia_anual` (`cod_municipio × año × etapa`, con nombres DIVIPOLA y la clase
`indagacion`/`judicializado`/`desconocido`) y `justicia_resumen` (por municipio: `total_procesos`,
`n_judicializados` y **`tasa_judicializacion_pct`** = 100·judicializados / procesos de etapa conocida). La
clasificación de etapa es robusta a tildes/mayúsculas (`_clasifica_etapa`).

**Cifras nacionales reales** (`reports/justicia.json`, regenerado por `vigia justicia`):

| Métrica | Valor |
|---|---|
| Procesos totales | **23.029.390** |
| Embudo | Indagación 21.069.716 (91,5 %) · **Judicializado 1.959.486 (8,5 %)** · desconocido 188 |
| **Tasa de judicialización nacional** | **8,51 %** |
| Top municipios (procesos · tasa) | Bogotá 5,5 millones · 5,6 % — Medellín 1,7 millones · 7,9 % — Cali 1,28 millones · 7,8 % — Barranquilla 707.000 · 9,0 % — Cartagena 512.000 · 6,5 % |

> El hallazgo es contundente y honesto: **solo ~8,5 % de las noticias criminales superan la indagación** a
> nivel nacional; las grandes ciudades quedan **por debajo** del promedio (Bogotá 5,6 %). Es una señal de
> *cuello de botella judicial* que el conteo de delitos no puede dar.

**Advertencias de uso:**
> 1. **Rezago judicial** — un proceso por un hecho reciente puede seguir en indagación o sin radicar, así que
>    los años recientes **subcuentan** más que la serie de la Policía.
> 2. **La indagación domina** el volumen (la mayoría de noticias no avanza); por eso el valor está en la
>    **tasa** de judicialización, no en el conteo bruto.
> 3. **No es comparable 1:1 con la Policía**: *proceso* (Fiscalía) ≠ *hecho registrado* (Policía), y la
>    taxonomía penal de la Fiscalía no mapea 1:1 a las categorías de delito de la Policía.
> 4. Unos pocos códigos DANE del hecho no cruzan con DIVIPOLA (extranjeros/sin dato) → quedan con nombre nulo
>    (de ahí 1.126 municipios vs. 1.122 oficiales).

> **Estado:** capa **cableada de punta a punta**. Produce los `gold` (`justicia_resumen`,
> `justicia_anual`) y `reports/justicia.json`; `etl/load.py` los carga a PostgreSQL; el backend expone
> `/justicia/resumen|municipios|departamentos|municipio`; el frontend tiene la pestaña pública **Justicia**;
> y `rag/ingest._justicia_cards` indexa el embudo para el asistente. Todo se genera con `make docker-pipeline`.

## Esquema crudo — Familia A (ej. homicidios `m8fd-ahd9`)

| Columna | Tipo | Ejemplo |
|---|---|---|
| `fecha_hecho` | fecha ISO | `2003-01-01T00:00:00.000` |
| `cod_depto` | texto | `11` |
| `departamento` | texto | `BOGOTA D.C.` |
| `cod_muni` | texto | `11001` |
| `municipio` | texto | `BOGOTA D.C.` |
| `zona` | texto | `URBANA` / `RURAL` |
| `sexo` | texto | `MASCULINO` |
| `arma_medio` | texto | `ARMA DE FUEGO` |
| `_modalidad_presunta` | texto | `RIÑAS` |
| `spoa_caracterizacion` | texto | `HOMICIDIO INTENCIONAL O CON DOLO` |
| `cantidad` | entero (texto) | `1` |

## Esquema crudo — Familia B (ej. violencia intrafamiliar `vuyt-mqpw`)

| Columna | Tipo | Ejemplo |
|---|---|---|
| `departamento` | texto | `CALDAS` |
| `municipio` | texto | `Manizales (CT)` |
| `codigo_dane` | texto (8 díg.) | `17001000` |
| `armas_medios` | texto | `SIN EMPLEO DE ARMAS` |
| `fecha_hecho` | fecha `dd/mm/yyyy` | `10/03/2026` |
| `genero` | texto | `FEMENINO` |
| `grupo_etario` | texto | `ADULTOS` |
| `cantidad` | entero (texto) | `2` |

## Tabla maestra de nombres — DIVIPOLA (DANE)

| Fuente | SODA id | Uso |
|---|---|---|
| DIVIPOLA — Códigos cabeceras / centros poblados | `xaxy-8nri` | **Fuente oficial de nombres** de departamentos y municipios + coordenadas |

Los nombres de `departamento` y `municipio` de la capa silver **no** se toman de las fuentes
delictivas (que tienen escrituras inconsistentes: con/sin tilde, sufijos, etc.), sino que se asignan
desde **DIVIPOLA** mediante cruce por el **código DANE de municipio** (`cod_municipio`). Esto garantiza
nombres oficiales y únicos (`BOGOTÁ, D.C.`, `MEDELLÍN`). De DIVIPOLA se toma además la **coordenada de
la cabecera municipal** (tipo `CM`) para el mapa del tablero. Implementado en
[`ml/vigia/etl/divipola.py`](../ml/vigia/etl/divipola.py).

## Población municipal — denominador para tasas por 100.000 habitantes (DANE)

Para expresar la criminalidad como **tasa por 100.000 habitantes** (comparable entre Bogotá y un municipio
pequeño) y como **feature exógena** del pronóstico, se incorpora la población municipal oficial del DANE.

| Fuente | Cobertura | Uso |
|---|---|---|
| *Proyecciones de población municipal por área (CNPV 2018, post-COVID)* | 2020-2035, nacional, ~1.122 municipios | Denominador de tasas + feature `log_poblacion`/`tasa_hist` |
| *Retroproyección de población municipal por área* | 2005-2019, nacional | Cubre el histórico de la serie delictiva |

> **Por qué NO viene de datos.gov.co.** El portal de datos abiertos **no publica una serie nacional
> municipal de población por año** (solo cargas sueltas de municipios/departamentos individuales —Chiquinquirá
> `stc8-i9y9`, Sabaneta, Cesar `izcs-53da`, etc.—, inservibles para cubrir los ~1.122 municipios; verificado
> consultando el *Asset Inventory* `uzcf-b9dh` sin filtrar categoría, por nombre y por fecha de
> actualización). <br/>
> La fuente oficial es el **DANE** (`dane.gov.co`), dato abierto de una entidad pública. Se descarga de:
> - `…/censo2018/proyecciones-de-poblacion/Municipal/DCD-area-proypoblacion-Mun-2020-2035-ActPostCOVID-19.xlsx`
> - `…/censo2018/proyecciones-de-poblacion/Municipal/DCD-area-proypoblacion-Mun-2005-2019.xlsx`

Ambos archivos comparten columnas (`DP, DPNOM, MPIO, DPMP, AÑO, ÁREA GEOGRÁFICA, Población`) aunque difieren
en hoja, fila de encabezado y orden → el parser localiza el encabezado y selecciona **por nombre** (se toma
solo `ÁREA GEOGRÁFICA = Total`). Implementado en [`ml/vigia/etl/poblacion.py`](../ml/vigia/etl/poblacion.py);
se materializa en `data/bronze/poblacion.parquet` (`[cod_municipio, anio, poblacion]`, con linaje en
`poblacion.meta.json`) y se cruza en `gold` por `(cod_municipio, anio)` con *clip* de año para respaldar los
extremos (2003-2004 → 2005; años futuros → 2035). Cobertura del cruce: **100 %** de la serie mensual.

## Esquema unificado — `data/silver/eventos.parquet`

| Campo | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Fecha del hecho (interpretada y validada) |
| `anio`, `mes` | int | Derivados de `fecha` |
| `cod_departamento` | str(2) | Código DANE departamento |
| `departamento` | str | Nombre normalizado (MAYÚSCULAS) |
| `cod_municipio` | str(5) | Código DANE municipio |
| `municipio` | str | Nombre normalizado |
| `zona` | str | `URBANA`/`RURAL`/`NO REPORTADO` |
| `categoria` | str | Categoría de delito (de `tipo_delito` o `tipo_de_hurto`; si no, la de la fuente) |
| `arma_medio` | str | Arma o medio empleado |
| `sexo` | str | `MASCULINO`/`FEMENINO`/`NO REPORTADO` |
| `grupo_etario` | str | Grupo etario (familia B) o `NO REPORTADO` |
| `cantidad` | int | Número de hechos |
| `fuente` | str | id del dataset de origen |
| `ingested_at` | datetime | Marca de linaje |

> La dimensión **`naturaleza`** (`delito` / `respuesta`) **no** se almacena en silver: se deriva en gold a
> partir de `categoria` (`datasets.naturaleza`, ver `RESPONSE_CATEGORIES`), para separar la incidencia
> delictiva de la respuesta institucional (capturas/incautaciones/recuperaciones) en los agregados.

## Esquema gold y tablas en PostgreSQL

`gold` produce tres parquet (`serie_mensual`, `resumen_municipio`, `resumen_categoria`) y `etl/load.py`
carga **cinco tablas** a PostgreSQL: las **tres de la capa de delito** que se documentan abajo
(`serie_mensual`, `resumen_municipio`, `anomalias`) más las **dos de la capa Justicia** (`justicia_resumen`,
`justicia_anual`, documentadas en su propia [sección](#capa-justicia--fiscalía-general-de-la-nación-fuente-de-otra-entidad-capa-paralela)).
`resumen_categoria` se computa pero hoy **no** se expone ni se consume; el backend deriva sus agregados de las tablas
de abajo. Los esquemas viven en el código que las inserta (`etl/load.py`), no en migraciones aparte.

**`serie_mensual`** — serie `municipio × categoría` mensual. Clave lógica `(cod_municipio, categoria, anio, mes)`.

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_municipio` | TEXT | Código DANE municipio |
| `municipio`, `cod_departamento`, `departamento` | TEXT | Nombres/códigos oficiales (DIVIPOLA) |
| `categoria` | TEXT | Categoría de delito o respuesta |
| `naturaleza` | TEXT | `delito` / `respuesta` (derivada de `categoria`) |
| `periodo` | DATE | Primer día del mes |
| `cantidad` | BIGINT | Hechos del mes (suma) |
| `anio`, `mes` | INT | Derivados de `periodo` |

> El parquet `serie_mensual.parquet` lleva además la columna **`poblacion`** (DANE, por `cod_municipio×anio`)
> que usa el modelo para las tasas/feature exógena; **no** se carga a la tabla PostgreSQL (el backend no la
> expone), por eso no figura en la lista de columnas de `etl/load.py`.

**`resumen_municipio`** — agregado por municipio (KPIs, ranking y mapa).

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_municipio`, `municipio`, `departamento` | TEXT | Identificación oficial (DIVIPOLA) |
| `total_hechos` | BIGINT | Gran total (delitos + respuestas) |
| `total_delitos` | BIGINT | Solo delitos (lo que usan KPIs/ranking/mapa) |
| `total_respuestas` | BIGINT | Solo respuesta institucional |
| `categorias` | INT | Nº de categorías distintas con datos |
| `primer_anio`, `ultimo_anio` | INT | Rango temporal cubierto |
| `lat`, `lon` | DOUBLE PRECISION | Coordenada de la cabecera (DIVIPOLA) para el mapa |

**`anomalias`** — alertas tempranas detectadas (`ml/anomaly.py`). Solo categorías de **delito**.

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_municipio`, `municipio`, `departamento`, `categoria` | TEXT | Identificación del hecho atípico |
| `periodo` | DATE | Mes de la anomalía |
| `cantidad` | BIGINT | Conteo observado |
| `score_z` | DOUBLE PRECISION | z robusto (intensidad de la atipicidad) |
| `severidad` | TEXT | `ALTA` (\|z\|>5) / `MEDIA` |

Índices: `serie_mensual (cod_municipio, categoria)`; `resumen_municipio (total_delitos DESC)`; `anomalias
(periodo DESC, cod_municipio)` + índices GIN `pg_trgm` para la búsqueda textual sin acentos (ver `load.py`).

## Documentos no estructurados — base de conocimiento del RAG (`data/kb_docs/`)

Además de los datasets estructurados, la base de conocimiento del asistente indexa **documentos**
(PDF/Word) de política pública. Se colocan en `data/kb_docs/` (`settings.rag_docs_dir`, montado en el
contenedor) y `docker-rag-index` los procesa (`pypdf`/`python-docx`), los parte en fragmentos solapados
(~800 caracteres, solape 150) y los indexa en `kb_chunks` junto a las *data cards* de gold. Implementado
en [`ml/vigia/rag/documents.py`](../ml/vigia/rag/documents.py).

**Procedencia del documento incluido.** El PDF versionado (*Política de Seguridad, Defensa y Convivencia
Ciudadana 2022-2026*, Ministerio de Defensa Nacional) es la **copia íntegra y sin modificaciones** del
documento oficial publicado por la Policía Nacional en
[policia.gov.co](https://www.policia.gov.co/sites/default/files/2024-12/Pol%C3%ADtica%20de%20Seguridad%20Defensa%20y%20Convivencia%20Ciudadna.pdf)
*[sic: la errata «Ciudadna» de la URL es del sitio de origen]*
(verificado: mismo tamaño byte a byte, 47.785.152 bytes, que el original en línea; descargado en junio de
2026). Documento público oficial, redistribuido con cita de su fuente para que el pilar de datos no
estructurados sea **reproducible en un clon** sin depender de la disponibilidad del sitio de origen.

| Campo (metadata del chunk) | Valor | Uso |
|---|---|---|
| `tipo` | `"documento"` | Distingue la fuente (vs `municipio`/`categoria`/`ranking`/…) |
| `fuente` | nombre del archivo (sin extensión) | Cita: "Documento: …" |
| `pagina` | nº de página (solo PDF) | Cita "(pág. N)" para auditabilidad |

