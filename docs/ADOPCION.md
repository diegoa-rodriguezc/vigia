# Ruta de adopción y pilotaje

VigIA es una **plataforma funcional**, publicada como proyecto reutilizable.
Este documento es la propuesta concreta para que una entidad pública pueda adoptarla.

---

## 1. A quién le sirve (entidades objetivo)

| Tipo de entidad | Para qué la usaría |
|---|---|
| **Secretarías de Seguridad** (municipales/departamentales) | Insumo de evidencia para Consejos de Seguridad: pronóstico, alertas y priorización |
| **Gobernaciones / Alcaldías** | Focalización del gasto en seguridad y rendición de cuentas |
| **Observatorios de seguridad / del delito** | Tablero y modelo reproducible sin construir capacidad de datos desde cero |
| **Policía Nacional (DIJIN / oficinas regionales)** | Lectura territorial unificada de sus propios datos abiertos |
| **Think tanks y academia** (p. ej. FIP, universidades) | Base reproducible para análisis de política pública |

**Énfasis territorial:** las regiones priorizadas por el concurso (Amazonía, Orinoquía, San Andrés) son
también las de menor capacidad analítica instalada — donde una herramienta ya construida y reproducible tiene
**más** valor marginal (ver cobertura en [docs/IMPACTO.md](IMPACTO.md#4-valor-territorial-diferenciado)).

---

## 2. Qué pone cada parte

- **VigIA aporta:** el código abierto (MIT), el pipeline reproducible, el modelo, el tablero y la
  documentación. Cero costo de licencia de datos (todo es abierto).
- **La entidad aporta:** un equipo mínimo (un analista de datos + un referente de seguridad), un servidor
  (dimensionado abajo) y, opcionalmente, sus propios datos internos para enriquecer el modelo.

### Dimensionamiento y costo de operación (órdenes de magnitud)

- **Servidor:** 4 vCPU / **16 GB de RAM** / ~30 GB de disco corren la plataforma completa, incluido el LLM
  local (la plataforma ocupa ~20 GB —el requisito mínimo declarado en el [README](../README.md#-instalación)—;
  el resto es margen operativo para logs y crecimiento del lago de datos). En nube, una máquina de ese tamaño cuesta ≈ **USD 50–100/mes** (~$2,5–5 millones COP/año); también
  sirve hardware propio reutilizado. Con un **proveedor gestionado de LLM** (`LLM_PROVIDER=anthropic|openai`
  por `.env`) el requisito baja a ~8 GB de RAM (sin Ollama) y el asistente cuesta **centavos de dólar por
  consulta**, amortiguado por la caché en Redis (cada respuesta se computa una vez por TTL).
- **Licencias:** $0 — software MIT y datos 100 % abiertos.
- **Operación recurrente:** el runbook mensual
  ([CRISP-ML-Q §6.6](CRISP-ML-Q.md#66-runbook-mensual-operación-mínima-sin-automatización)) — regenerar el
  pipeline al publicarse el mes nuevo y revisar el semáforo de *Salud del modelo* — cabe en **~medio día al
  mes** de la persona analista.
- **Riesgo operativo principal y su mitigación:** un cambio de esquema en la API SODA2 de una fuente. El
  catálogo es **declarativo** (`ml/vigia/datasets.py`) y la re-ingesta selectiva
  (`make docker-reingest ONLY=<fuente>`) acota la reparación a la fuente afectada; el semáforo de
  **frescura** detecta cuándo una fuente dejó de actualizarse.

---

## 3. Plan piloto a 30 / 60 / 90 días

**Días 0–30 — Despliegue y validación de datos.**
- Levantar VigIA con `make deploy` (datos abiertos nacionales ya incluidos).
- Sesión de validación con el equipo de la entidad: ¿los municipios, las cifras y las categorías coinciden
  con su conocimiento del territorio?
- Definir las 2–3 categorías de delito de mayor prioridad local.

**Días 31–60 — Uso asistido en el ciclo de decisión.**
- Integrar el tablero al insumo del Consejo de Seguridad (pronóstico + alertas de las categorías priorizadas).
- Capacitación de la persona analista (media jornada): cómo leer la banda de incertidumbre, las anomalías y
  cómo interrogar al asistente.
- Primera recomendación basada en evidencia llevada a una instancia de decisión.

**Días 61–90 — Evaluación de valor.**
- Comparar la incidencia observada vs. la proyectada en las zonas donde hubo intervención (el bucle de
  evaluación de [docs/IMPACTO.md](IMPACTO.md#3-caso-de-uso-concreto-escenario-ilustrativo)).
- Recoger métricas de uso (consultas al asistente, alertas atendidas) y de percepción del equipo.
- Decisión de continuidad / escalamiento a más categorías o municipios.

**Criterios de éxito del piloto:**
- El equipo usa el tablero en al menos un Consejo de Seguridad.
- Se documenta al menos una decisión informada por VigIA.
- La entidad manifiesta la intención de continuar.

---

## 4. Por qué es de bajo riesgo para la entidad

- **Sin dependencia de proveedor:** software abierto, desplegable en su propia infraestructura.
- **Sin costo de datos:** 100 % datos abiertos (datos.gov.co + DANE).
- **Privacidad:** trabaja con **agregados** municipales, no con datos personales de víctimas.
- **Reversible:** si no aporta valor, se apaga; no crea dependencias críticas.

---

El repositorio es abierto y auditable: cualquier entidad, evaluador o ciudadano puede revisar el código,
los datos y la metodología desarrollada.
