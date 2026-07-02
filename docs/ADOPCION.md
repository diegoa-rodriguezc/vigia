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
  modesto (o una cuenta de nube) y, opcionalmente, sus propios datos internos para enriquecer el modelo.

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
- el equipo usa el tablero en al menos un Consejo de Seguridad
- se documenta al menos una decisión informada por VigIA
- la entidad manifiesta intención de continuar.

---

## 4. Por qué es de bajo riesgo para la entidad

- **Sin dependencia de proveedor:** software abierto, desplegable en su propia infraestructura.
- **Sin costo de datos:** 100 % datos abiertos (datos.gov.co + DANE).
- **Privacidad:** trabaja con **agregados** municipales, no con datos personales de víctimas.
- **Reversible:** si no aporta valor, se apaga; no crea dependencias críticas.

---

El repositorio es abierto y auditable: puede revisar el código, los
datos y la metodología desarrollada.
