# VigIA 🛡️ — Inteligencia Artificial para la Seguridad Ciudadana y la Justicia

> **Concurso Datos al Ecosistema 2026 — IA para Colombia** <br/>
> **Reto:** Seguridad Ciudadana y Justicia <br/>
> **Nivel:** Avanzado

**VigIA** (de *vigía* + *IA*) es una plataforma de analítica predictiva y asistencia ciudadana que
transforma los datos abiertos de criminalidad de Colombia en **alertas tempranas, pronósticos y
conocimiento accionable** para fortalecer las políticas públicas de seguridad y justicia.

---

## 🎯 Problema y propuesta de valor

Las entidades territoriales y la ciudadanía carecen de herramientas que conviertan el enorme volumen
de datos delictivos publicados por las Entidades Públicas en **decisiones preventivas**. VigIA responde con:

| Componente IA | Qué hace | Reto del concurso |
|---|---|---|
| 🔮 **Pronóstico espacio-temporal** | Predice la incidencia de delitos por municipio y mes, **con banda de incertidumbre** | Analítica predictiva |
| 🎛️ **Simulación de escenarios "¿y si…?"** | Proyecta el efecto de una intervención o un cambio de población sobre el pronóstico y estima **hechos evitados** | Analítica prescriptiva |
| 🚨 **Detección de anomalías** | Identifica picos atípicos de criminalidad relativos a cada territorio (alerta temprana) | Detección de anomalías |
| 💬 **Asistente ciudadano (agente con herramientas)** | Responde en lenguaje natural usando solo datos oficiales; el LLM **elige y encadena herramientas** (pronóstico, anomalías, embudo de Justicia, serie histórica, base de conocimiento) y cita cada cifra | IA generativa + agente de IA |
| 📝 **Informe de seguridad municipal** | Genera un **informe ejecutivo** por municipio (panorama, alertas, pronóstico, judicialización) **anclado a las cifras oficiales** (`vigia brief` / `GET /brief`) | IA generativa (reportes automatizados) |
| 🩺 **Salud del modelo (monitoreo)** | Vigila **frescura** de datos, **deriva (PSI - Population Stability Index)** y validación a **12 meses** con semáforo, sin reentrenar | Calidad y gobierno del modelo |
| ⚖️ **Embudo de judicialización (Fiscalía)** | Mide qué fracción de las noticias criminales avanza en la cadena penal (tasa de judicialización por municipio) | Eje de **Justicia** |
| 📊 **Tablero interactivo** | Mapas, series y rankings por territorio | Visualización |

## 🖼️ El tablero en imágenes

> El tablero cuenta con ocho vistas/pestañas. **Pronóstico**, **Simulador**, **Asistente** e **Informe** requieren
> inicio de sesión (cómputo de IA protegido); **Panorama**, **Alertas**, **Justicia** y **Salud del modelo**
> son públicas. 

A continuación se presentan las capturas de pantalla de la aplicación:
| Panorama | Alertas tempranas |
|---|---|
| [![Panorama — KPIs, ranking y mapa coroplético](docs/screenshots/01-panorama.png)](docs/screenshots/01-panorama.png) | [![Alertas tempranas — anomalías por severidad](docs/screenshots/02-alertas.png)](docs/screenshots/02-alertas.png) |
| KPIs nacionales, ranking por municipio, top-10 y **mapa coroplético** por departamento. | Tabla de **anomalías** por severidad, búsqueda/filtros y la explicación del z-robusto. |

| Pronóstico  | Asistente ciudadano  |
|---|---|
| [![Pronóstico — historia, predicción y banda de incertidumbre](docs/screenshots/03-pronostico.png)](docs/screenshots/03-pronostico.png) | [![Asistente — respuesta con citación de fuente](docs/screenshots/04-asistente.png)](docs/screenshots/04-asistente.png) |
| Selección municipio × categoría con **historia + pronóstico + banda de incertidumbre** (80% nominal, **calibrada empíricamente** a 80% de cobertura real — ver [CRISP-ML(Q)](docs/CRISP-ML-Q.md#4-evaluación-del-modelo)). | Responde **solo con datos oficiales** y **cita cada cifra** (chips de fuente). En el modo por defecto (**Ollama local**) usa **RAG clásico** —la captura—; con proveedor de *tool-use* (**Anthropic/OpenAI**) opera como **agente que elige y encadena herramientas** (pronóstico, anomalías, embudo de Justicia…). |

| Simulador  | Salud del modelo |
|---|---|
| [![Simulador — base vs escenario y hechos evitados](docs/screenshots/05-simulador.png)](docs/screenshots/05-simulador.png) | [![Salud del modelo — semáforo de frescura, deriva (PSI) y backtest 12m](docs/screenshots/06-salud.png)](docs/screenshots/06-salud.png) |
| Palancas de intervención/población con **base vs escenario** y el KPI de **hechos evitados** (supuesto del usuario, no efecto causal estimado por el modelo). | **Semáforo** de frescura, **deriva (PSI - Population Stability Index)** y backtest a 12 meses con la degradación del error por horizonte. |

| Justicia | Informe (IA generativa) |
|---|---|
| [![Justicia — embudo de judicialización de la Fiscalía](docs/screenshots/07-justicia.png)](docs/screenshots/07-justicia.png) | [![Informe — informe ejecutivo municipal generado por IA](docs/screenshots/08-informe.png)](docs/screenshots/08-informe.png) |
| **Embudo de judicialización** de la Fiscalía (capa paralela): tasa nacional **8,51 %**, KPIs, barras por departamento y tabla por municipio. | **Informe ejecutivo municipal** generado por IA, **anclado a las cifras oficiales** (panorama, alertas, pronóstico, judicialización) con **chips auditables**. |

**Cómo usar la herramienta:** 

1. *Panorama* → ubica los territorios y delitos con mayor incidencia en el mapa y el ranking.
2. *Alertas tempranas* → revisa qué municipios tienen repuntes atípicos recientes (no solo volumen alto).
3. *Justicia* → consulta el embudo de judicialización de la Fiscalía y la tasa por municipio/departamento.
4. *Pronóstico* → proyecta un delito en un municipio a varios meses con su banda de incertidumbre.
5. *Simulador* → mueve las palancas de una intervención o un cambio de población y observa cuántos hechos se evitarían frente al pronóstico base.
6. *Asistente* → pregunta en lenguaje natural ("¿cuál fue el delito más frecuente en Cali?" o "¿cómo se proyectan los hurtos en Medellín?") y recibe una respuesta con su respectiva fuente.
7. *Informe* → genera un informe ejecutivo del municipio (panorama, alertas, pronóstico y judicialización), también accesible desde el botón **Generar informe** del drill-down del Panorama.
8. *Salud del modelo* → revisa el semáforo de frescura, deriva (PSI - Population Stability Index) y la validación del pronóstico a 12 meses.

## 🧱 Arquitectura

![Arquitectura de componentes de VigIA: tres capas desacopladas (React, Go y Python/FastAPI) sobre PostgreSQL + pgvector, con Redis y Ollama como servicios de apoyo, alimentadas por datos abiertos de datos.gov.co, DANE y Fiscalía](docs/diagrams/arquitectura.png)

> Diagrama editable: [`docs/diagrams/arquitectura.excalidraw`](docs/diagrams/arquitectura.excalidraw) (abrirlo en [excalidraw.com](https://excalidraw.com)).

Detalle completo en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 🗂️ Estructura del repositorio

```
vigia/
├── data/                  # Lago de datos medallion (bronze/silver/gold) — no versionado
├── docs/                  # Documentación general (arquitectura, CRISP-ML(Q), diccionario, etc.)
├── notebooks/             # Exploración y perfilado (EDA) de las fuentes
├── ml/                    # Python: ETL + Machine Learning + RAG + API (FastAPI)
├── backend/               # Go: API REST / BFF
├── frontend/              # React + TypeScript: tablero y asistente
├── db/                    # Esquema SQL e inicialización (PostgreSQL + pgvector)
├── docker-compose.yml     # Orquestación de todos los servicios
└── Makefile               # Atajos del ciclo de vida del proyecto
```

> [!NOTE]
> El presente proyecto tiene una implementación de un RAG (Retrieval-Augmented Generation), por lo cual 
> si su equipo tiene tarjeta gráfica (ej. NVIDIA), se recomienda realizar los pasos mencionados en la sección
> [Aceleración por GPU](#aceleración-por-gpu-opcional) para su despliegue; de lo contrario, realice
> la [Ejecución en CPU](#ejecución-en-cpu), lo cual influye en el tiempo de despliegue del proyecto.

## 🚀 Instalación

> **Requerimientos:**
> - *Sistema operativo:* Windows 10/11, macOS 10.15 o superior, Linux (distribución a su elección).
> - Tener instalado [Docker](https://www.docker.com/products/docker-desktop/)
> - Tener instalado [Git](https://git-scm.com/) y/o [GitHub Desktop](http://github.com/apps/desktop)
> - Tener instalado Make
>    - En **Windows** se instala mediante una terminal/PowerShell ejecutando el siguiente comando
>    ```cmd
>    winget install ezwinports.make
>    ```
>    - En **Linux** se instala mediante una terminal ejecutando el siguiente comando
>    ```bash
>    # comando para distribuciones Debian/Ubuntu, ajustar según el manejador de paquetes de su distribución
>    sudo apt-get install build-essential -y
>    ```

### Ejecución en CPU

En una ventana de comandos (cmd/terminal), ejecutar los comandos que a continuación se describen:

1. Clone el repositorio (donde se ejecute el comando es donde se va a almacenar el código)
```bash
git clone https://github.com/diegoa-rodriguezc/vigia.git
```

2. Ingrese a la carpeta del proyecto previamente clonado (`vigia`)
```bash
cd vigia
```

3. Realice la copia del archivo `.env.example` y **edite** los valores del archivo `.env` según corresponda
```bash
cp .env.example .env          # ajustar las credenciales según corresponda el ambiente (dev/prod)
```

4. Para levantar los servicios se debe tener en ejecución e instalado **Docker** e instalado **Make** (ver requisitos)
```bash
make deploy                   # up + descarga de modelos + pipeline con datos (todo en Docker)
```

Con el anterior comando, se levantan los contenedores de Docker con las imágenes necesarias para el despliegue del proyecto. *Este proceso puede tomar alrededor de 1 hora, debido a la descarga de fuentes de información, así como la indexación de información usada por el RAG en CPU.*

> [!TIP] Para listar más comandos utilice `make help`, lista todos los atajos disponibles con su descripción.

### Aceleración por GPU (opcional)

> Requisitos: driver NVIDIA + **NVIDIA Container Toolkit** (Linux) o **Docker Desktop con backend WSL2**
> y driver NVIDIA con soporte WSL (Windows).

En una ventana de comandos (cmd/terminal), ejecutar los comandos que a continuación se describen:

1. Clone el repositorio (donde se ejecute el comando es donde se va a almacenar el código)
```bash
git clone https://github.com/diegoa-rodriguezc/vigia.git
```

2. Ingrese a la carpeta del proyecto previamente clonado (`vigia`)
```bash
cd vigia
```

3. Realice la copia del archivo `.env.example` y **edite** los valores del archivo `.env` según corresponda
```bash
# ajustar las credenciales según corresponda el ambiente (dev/prod)
cp .env.example .env
```

4.  Ejecute el comando para despliegue en GPU
```bash
# ejecución en GPU
make deploy-gpu      
```

Con el anterior comando, se levantan los contenedores de Docker con las imágenes necesarias para el despliegue del proyecto. *Este proceso puede tomar alrededor de 30 min, debido a la descarga de fuentes de información e indexación de información usada por el RAG.*

## Acceso a la aplicación

Una vez levantado/desplegado el proyecto, se puede ingresar mediante un navegador a través de la URL
- `http://localhost:5173`



## 📐 Metodología

El proyecto sigue la metodología **CRISP-ML(Q)** (Cross-Industry Standard Process for Machine Learning with Quality
assurance). Cada fase, sus controles de calidad y riesgos están documentados en
[docs/CRISP-ML-Q.md](docs/CRISP-ML-Q.md).

## 🔓 Datos abiertos utilizados

**20 conjuntos de datos abiertos** de [datos.gov.co](https://www.datos.gov.co/browse?category=Seguridad+y+Defensa)
consumidos vía **API SODA2**. Su composición:

- **16 de eventos de la Policía** (catálogo *Seguridad y Defensa*) que conforman la serie unificada: **13 de
  delito** y **3 de respuesta institucional** (capturas, incautaciones y recuperaciones, separadas en la capa
  gold para no confundirlas con la incidencia ni dispararlas como alertas).
- **2 administrativos** (auditorías y demandas), que alimentan el asistente como contexto de transparencia.
- **1 de referencia oficial** — **DIVIPOLA** del DANE, para nombres y coordenadas.
- **1 de la Fiscalía General de la Nación** (*otra entidad*), que añade el eje de **Justicia** (abajo).

Los 20 se **alojan en datos.gov.co** —incluidos DIVIPOLA y *Procesos Fiscalía*, producidos por otras
entidades pero publicados allí—. La **población municipal del DANE** (sección más abajo) es una referencia
demográfica **adicional** que **no entra** en este conteo de 20. Las 16 fuentes de eventos se seleccionaron
del *Asset Inventory* oficial de la categoría (`uzcf-b9dh`, ~169 datasets **consultados**) por relevancia,
esquema y no duplicación. Inventario, selección y descartes justificados en
[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) y [docs/DATASETS.md](docs/DATASETS.md). La
**alineación con la Hoja de Ruta Nacional de Datos Abiertos Estratégicos** se detalla en la sección
siguiente.

**Eje de Justicia — Fiscalía General de la Nación.** Para no depender de una sola entidad (la Policía) y
cubrir la mitad de *"Justicia"* del reto, VigIA incorpora el dataset *Procesos Fiscalía V3* (`dbdv-iihs`,
~23 M de procesos) como **capa paralela**: aporta la sección **judicialización** (Indagación → Investigación
→ Juicio → Ejecución de Penas), una señal que ningún conteo de delitos tiene. Hallazgo nacional real: **solo
~8,5 % de las noticias criminales superan la indagación** (Bogotá, 5,6 %). No se fusiona con la serie de la
Policía (*proceso* ≠ *hecho registrado* → sería doble conteo). Como su API de agregación no es viable a ese
volumen, se ingiere por **streaming keyset + agregación local** (reproducible sin token). Detalle, cifras y
*Advertencias de uso* en [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md#capa-justicia--fiscalía-general-de-la-nación-fuente-de-otra-entidad-capa-paralela).

**Contexto demográfico — población municipal (DANE).** Para medir la criminalidad como **tasa por 100.000
habitantes** (comparable entre territorios) y enriquecer el pronóstico con una señal **exógena** (no solo
autorregresiva), se incorpora la **proyección/retroproyección de población municipal por área del DANE**
(2005-2035, nacional). datos.gov.co **no** publica esta serie nacional municipal —solo cargas sueltas por
municipio—, así que se usa el archivo oficial de [`dane.gov.co`](https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion),
dato abierto de entidad pública admitido por el concurso. Detalle en
[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md#población-municipal--denominador-para-tasas-por-100k-dane).

**Datos estructurados + no estructurados.** Además de las series, el asistente RAG indexa **documentos de
política pública** (PDF/Word) para responder sobre el marco normativo citando la fuente **por página**
(p. ej. la *Política de Seguridad, Defensa y Convivencia Ciudadana 2022-2026* del Ministerio de Defensa).
Para incluir documentos, se deben colocar en la carpeta `data/kb_docs/` y ejecutar `docker compose exec ml python -m vigia rag-index` con el fin de indexar los documentos y que sean tenidos en cuenta para las respuestas del RAG.

## 🗺️ Alineación con las Hojas de Ruta de Datos Abiertos Estratégicos

VigIA se construye sobre el conjunto **priorizado por la Hoja de Ruta Nacional
de Datos Abiertos Estratégicos 2025-2026** ([`fn2v-r4gu`](https://www.datos.gov.co/resource/fn2v-r4gu.json),
categoría **DEFENSA**, registro **id 70**, entidad responsable **Ministerio de Defensa — Observatorio de
Derechos Humanos y Defensa Nacional**):

| Fuente VigIA | SODA2 | Alineación con la Hoja de Ruta Nacional |
|---|---|---|
| Homicidios | `m8fd-ahd9` | ✅ Enlazada nominalmente (DEFENSA, id 70) |
| Hurto a residencias | `7mn7-vzqp` | ✅ Enlazada nominalmente (DEFENSA, id 70) |
| Delitos informáticos | `4v6r-wu98` | ✅ Enlazada nominalmente (DEFENSA, id 70) |
| Delitos sexuales | `bz43-8ahq` | ✅ Enlazada nominalmente (DEFENSA, id 70) |
| Otras 12 fuentes de eventos (9 de delito + 3 de respuesta) | (ver diccionario) | ◐ Mismo conjunto priorizado *"Estadísticas de criminalidad"*; materializan la recomendación de **consolidar** |

Detalle del mapeo y la verificación contra la API en [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) y
[docs/DATASETS.md](docs/DATASETS.md).

## 🌎 Impacto, escalabilidad y enfoque territorial

**Problema.** El crimen y la violencia le cuestan a Colombia **el 3,64 % del PIB —unos $68 billones al año— (Fedesarrollo–BID, 2022)**[^costo], 
repartidos entre capital humano (0,88 %), sector privado (1,76 %) y sector público (1,0 %). En el plano social, la **percepción de
inseguridad llegó al 52,9 %** de la población de 15+ años (**DANE, Encuesta de Convivencia y Seguridad
Ciudadana 2024**)[^dane], y el país registra **~25 homicidios por cada 100.000 habitantes (~13–14 mil al
año)**[^hom]. Una fracción pequeña de ese gasto, reasignada con **anticipación** a la prevención, tiene un
retorno social y fiscal alto: ese es el espacio donde VigIA genera valor.

**Beneficiarios.** Las entidades territoriales rara vez disponen de pronósticos y alertas accionables a
nivel municipal. VigIA está pensada para **secretarías de seguridad y convivencia, alcaldías y
gobernaciones, observatorios del delito, los Consejos de Seguridad territoriales, la Policía Nacional y la
Fiscalía**, que pueden anticipar la asignación de recursos preventivos y priorizar territorios con repuntes
atípicos.

> **Ejes de impacto.** El aporte de VigIA es **social** (prevención del delito, control social ciudadano) y
> **económico** (uso más eficiente del gasto preventivo). El eje **ambiental no aplica** a este reto de
> seguridad ciudadana.

**Mecanismo de impacto.** 
1. *Pronóstico por municipio×delito* con banda de incertidumbre → planeación preventiva con horizonte de meses.
2. *Alertas de anomalías* → reacción temprana ante repuntes.
3. *Asistente ciudadano* → acceso abierto y transparente a la cifra oficial, fortaleciendo el control
social. El valor está en reasignar el esfuerzo preventivo **antes** de que el delito escale.


**Enfoque territorial.** Por estar construida sobre el código DANE y DIVIPOLA, VigIA
cubre **todo el territorio nacional** (1.106 de 1.126 municipios modelados). En las regiones que el concurso
prioriza por su menor participación digital, la cobertura concreta es:

| Región | Municipios modelados | Series modeladas | Hechos delictivos | Población |
|---|---|---|---|---|
| **Amazonía** | 44 / 56 | 498 | 118.731 | 1,13 M |
| **Orinoquía** | 58 / 60 | 768 | 313.726 | 2,12 M |
| **San Andrés y Providencia** | 2 / 2 | 21 | 14.300 | 62 k |

Los municipios **no** modelados (p. ej. Guainía 1/6, Vaupés 3/5) son los de la Amazonía profunda cuya serie
es demasiado dispersa (<12 meses con hechos) para un pronóstico fiable — y esa **escasez de dato es en sí un
hallazgo**: VigIA la hace visible con dato oficial en vez de ocultarla. La teoría de cambio y el valor para
estas regiones se detallan en [docs/IMPACTO.md](docs/IMPACTO.md).

También se puede consultar la arquitectura de la aplicación en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 👥 Equipo

| Integrante | Rol | Género |
|---|---|---|
| Jeraldine Mora Lavado | Ciencia de datos | F |
| Jorge Esneider Henao González | Desarrollo / Backend | M |
| Héctor Leandro Rojas Serrano | Análisis de datos | M |
| Diego Alberto Rodríguez Cruz | Líder / Arquitectura / ML | M |

## 🔐 Seguridad y acceso

VigIA usa un **modelo de acceso híbrido** que preserva la transparencia de los datos abiertos y a la vez
blinda los recursos costosos:

- **Público (con *rate-limiting*):** panorama, mapa, alertas y series.
- **Protegido con JWT:** el **pronóstico**, el **simulador**, el **asistente** y el **informe** (cómputo de IA), para evitar abuso/DoS.

Cualquier ciudadano puede **crear una cuenta** (rol `citizen`) desde `POST /auth/register` —o el botón
*Crear cuenta* del tablero— y usar así las funciones de IA **sin depender de la cuenta administradora**: el
"asistente ciudadano" es realmente de acceso ciudadano. El registro aplica la misma política de contraseña
que el admin y está limitado por IP para evitar altas masivas. Para un despliegue **institucional cerrado**,
`REGISTRATION_ENABLED=false` deshabilita el alta pública (el servidor responde `403` y la UI oculta el botón).

La autenticación es **JWT (access token corto) + refresh token rotativo en Redis**, con revocación
(logout), hashing **bcrypt**, bloqueo contra ataques de fuerza bruta, *rate-limiting* y cabeceras de seguridad.
Configurable por `.env` (`JWT_SECRET`, `JWT_EXPIRATION`, `JWT_REFRESH_EXPIRATION`, `ADMIN_*`). En
producción (`APP_ENV=production`) el backend **aborta si `JWT_SECRET` o `ADMIN_PASSWORD` siguen en sus
valores públicos por defecto** (los que trae el repositorio) o si la contraseña es débil (fail-closed); en
desarrollo se permiten con un aviso, para no frenar la demo. La ciudadanía se
da de alta con rol `citizen` vía `POST /auth/register`; el usuario **administrador** se inserta al arrancar
con `ADMIN_USERNAME`/`ADMIN_PASSWORD`. Detalle en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#6-decisiones-de-arquitectura-adr-resumidos) (ADR-05).

## ⚖️ Ética y reproducibilidad

VigIA usa exclusivamente **datos públicos y agregados** (sin información personal identificable), en línea
con la Ley 1581 de 2012 (Habeas Data). Los pronósticos son una **ayuda a la decisión**, no un mecanismo de
vigilancia individual ni de *policing* predictivo sobre personas. Frente al **bucle de retroalimentación**
del *policing* predictivo (más patrullaje → más hechos registrados → más predicción), VigIA lo **acota por
diseño**: granularidad territorial agregada (no individual), anomalías relativas a cada serie (no se
concentran en las ciudades grandes), exclusión de la actividad policial de las alertas, aviso de uso
responsable en la pestaña *Alertas* y en el *prompt* del asistente, y la decisión de despliegue en manos del
equipo humano. El sesgo de subregistro/despliegue subyacente **no se elimina** (no hay variable de exposición
abierta) y se declara como tal. Detalle en
[docs/CRISP-ML-Q.md](docs/CRISP-ML-Q.md#el-bucle-de-retroalimentación-del-policing-predictivo-y-cómo-se-acota).

**Publicación.**
El código fuente, la documentación y la evidencia de uso de datos abiertos están disponibles: en el repositorio 
- Repositorio de acceso público [github.com/diegoa-rodriguezc/vigia](https://github.com/diegoa-rodriguezc/vigia), garantizando que la
solución sea verificable, descargable y auditable. 
- El registro en la sección de **usos de datos.gov.co**
([herramientas.datos.gov.co/usos](https://herramientas.datos.gov.co/usos)) se realizará al momento de la
entrega y evaluación.

## 📄 Licencia

MIT — ver [LICENSE](LICENSE). 

---

**Referencias**
[^costo]: Estudio de Fedesarrollo y el Banco Interamericano de Desarrollo (BID): los costos del crimen y la
    violencia en Colombia equivalen al **3,64 % del PIB (~$68 billones, 2022)**. Reseñado en
    [Portafolio](https://www.portafolio.co/economia/regiones/cuanto-dinero-cuesta-la-situacion-de-violencia-en-colombia-617292)
    y [La Silla Vacía](https://www.lasillavacia.com/en-vivo/el-crimen-y-la-violencia-en-colombia-cuestan-un-3-6-del-pib/).
    Cifra regional comparable del BID: ~3,4 % del PIB para América Latina y el Caribe.

[^dane]: DANE — **Encuesta de Convivencia y Seguridad Ciudadana (ECSC) 2024**: la percepción de inseguridad
    alcanzó el **52,9 %** de la población de 15 años o más.
    [Boletín oficial (PDF)](https://www.dane.gov.co/files/operaciones/ECSC/bol-ECSC-2024.pdf).
    
[^hom]: Tasa de homicidios de **~25 por cada 100.000 habitantes** (~13–14 mil homicidios anuales, 2021–2024),
    según Policía Nacional / Instituto Nacional de Medicina Legal. Serie en
    [Corporación Excelencia en la Justicia](https://cej.org.co/indicadores-de-justicia/criminalidad/homicidios-en-colombia/)
    y dataset oficial [HOMICIDIO (datos.gov.co)](https://www.datos.gov.co/Seguridad-y-Defensa/HOMICIDIO/m8fd-ahd9).
