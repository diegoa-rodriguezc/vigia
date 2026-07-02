# Impacto, teoría de cambio y valor territorial

Este documento responde a la pregunta que el concurso pondera más alto (**Impacto y escalabilidad, 20 pts**):
¿qué problema real resuelve VigIA, cómo se traduce el dato en una decisión, y para quién?

---

## 1. El problema (cuantificado)

La inseguridad le cuesta a Colombia cerca del **3,64 % del PIB** (Fedesarrollo–BID, 2022) y **52,9 %** de la
población de 15 años o más se siente insegura (DANE, ECSC 2024). La Policía publica millones de registros delictivos
como dato abierto, pero **están dispersos en decenas de conjuntos, por tipo de delito, sin agregación ni
proyección**. El resultado: las entidades territoriales reaccionan a lo ya ocurrido en vez de anticiparlo, y
la ciudadanía no tiene una lectura clara de su entorno.

**El cuello de botella no es la falta de datos, es la falta de una capa que los convierta en decisión.**

---

## 2. Teoría de cambio

VigIA cierra el bucle **dato → conocimiento → decisión → acción → resultado**:

| Eslabón | Sin VigIA | Con VigIA |
|---|---|---|
| **Dato** | 16 fuentes de eventos dispersas (13 de delito), crudas | Un modelo unificado de eventos, tasas/100k comparables |
| **Conocimiento** | Reactivo: "¿cuántos hubo el mes pasado?" | Anticipatorio: pronóstico a 6 meses + alerta de anomalías + asistente que cita la fuente |
| **Decisión** | Por intuición o presión mediática | Priorización por municipio/categoría con evidencia y banda de incertidumbre |
| **Acción** | Despliegue homogéneo de pie de fuerza | Reasignación preventiva focalizada donde el riesgo proyectado sube |
| **Resultado** | Difícil de atribuir | Medible: comparar incidencia observada vs. proyectada tras la intervención |

**Persona usuaria principal:** el/la **analista de la Secretaría de Seguridad** (o del observatorio de
seguridad departamental), que prepara los insumos del Consejo de Seguridad. No es el alcalde: es quien
traduce el dato en recomendación operativa.

---

## 3. Caso de uso concreto *(escenario ilustrativo)*

> ⚠️ Escenario **ilustrativo** para explicar el flujo de valor, no un piloto ejecutado (ver
> [docs/ADOPCION.md](ADOPCION.md) para la ruta de pilotaje real).

1. **Señal.** En el tablero, la analista de la Secretaría de Seguridad de un municipio ve que el **pronóstico
   de hurto a personas** para el próximo trimestre sube de forma sostenida **en su municipio**, y que la pestaña
   de **Alertas** marcó una anomalía al alza el mes anterior **en ese municipio** para esa categoría. *(El
   horizonte servido es de 6 meses; el "próximo trimestre" se lee dentro de esa proyección.)*
2. **Contexto.** Consulta al **asistente** ("¿cómo viene el hurto a personas este año y cómo se compara con el
   resto del departamento?") y obtiene cifras citadas a la fuente oficial, sin tener que cruzar planillas.
3. **Decisión.** Lleva al Consejo de Seguridad una recomendación con evidencia: priorizar el **hurto a
   personas en ese municipio** durante el periodo proyectado, en vez de un despliegue homogéneo. VigIA aporta
   el *qué* (categoría), el *dónde* (municipio) y el *cuándo* (meses); el **detalle operativo fino —zona,
   barrio o franja horaria— lo añade el equipo local** con su conocimiento del territorio y los sistemas
   operativos de la Policía, que sí lo registran. *(El modelo trabaja a granularidad municipio × categoría ×
   mes; no pronostica por comuna ni por hora — ver acotación abajo.)*
4. **Acción.** Antes de fijar el nivel de esfuerzo, en el **Simulador** proyecta cuántos hurtos podrían
   evitarse bajo distintos supuestos de intervención (un **supuesto del usuario**, no un efecto causal estimado
   por el modelo). Con eso, la administración reasigna patrullaje preventivo focalizado al municipio y la
   categoría priorizados.
5. **Señal de evaluación.** Al mes siguiente, la analista compara la **incidencia observada contra la
   proyectada**: el pronóstico base —con su banda— funciona como **referencia esperada** sin intervención, de
   modo que si la serie real cae por debajo de lo proyectado, es una **señal** de que la acción pudo ayudar.
   No es prueba causal —no descuenta otros factores ni el subregistro—, pero da un criterio común para
   **evaluar** en vez de afirmar a ciegas.

El valor no es "predecir el crimen" con precisión perfecta —ningún modelo lo hace—, sino **dar una base de
evidencia común** para priorizar y para **evaluar** si lo que se hizo sirvió.

> **Acotación de granularidad (honestidad).** VigIA pronostica y alerta a nivel **municipio × categoría ×
> mes** —la granularidad que el dato abierto nacional publica de forma consistente para los 1.106 municipios
> modelados—.
> **No** desciende a comuna, barrio, cuadrante ni franja horaria: aunque algunas fuentes traen un campo `zona`
> (urbana/rural), su subregistro es alto (≈81% `NO REPORTADO`, ver
> [CRISP-ML(Q)](CRISP-ML-Q.md#2-ingeniería-de-datos-preparación)) y no sostendría un pronóstico intra-municipal
> fiable. El detalle táctico fino es competencia de los sistemas operativos internos de la Policía (SIEDCO/
> cuadrantes), no del dato abierto; VigIA prioriza **el municipio y el delito**, y el equipo local hace el
> *zoom*. Llevar el pronóstico a sub-municipio requeriría una fuente georreferenciada que hoy no es abierta —
> es una extensión natural si una entidad aporta sus datos internos (ver [ADOPCION.md](ADOPCION.md)).

---

## 4. Valor territorial diferenciado

El concurso prioriza explícitamente las regiones de menor participación digital. VigIA no solo "las cubre":
las **modela con dato oficial** y hace visible su subregistro.

| Región | Municipios modelados | Series modeladas | Hechos delictivos | Población |
|---|---|---|---|---|
| **Amazonía** | 44 / 56 | 498 | 118.731 | 1,13 M |
| **Orinoquía** | 58 / 60 | 768 | 313.726 | 2,12 M |
| **San Andrés y Providencia** | 2 / 2 | 21 | 14.300 | 62 k |

- Por construir sobre el **código DANE/DIVIPOLA** (no sobre los nombres inconsistentes de las fuentes), VigIA
  ubica correctamente municipios que los tableros nacionales suelen perder por errores de escritura.
- Las **tasas por 100.000 habitantes** (población DANE) hacen comparable un municipio amazónico de pocos
  miles con una capital — algo imposible con conteos crudos.
- Los municipios **no** modelados (Guainía 1/6, Vaupés 3/5, Amazonas 7/11) tienen series demasiado ralas
  (<12 meses con hechos). En vez de inventar un pronóstico falso, VigIA los **deja explícitos como vacío de
  información** — un insumo de política pública en sí mismo (¿por qué no se reporta?).

---

## 5. Impacto esperado

- **Social:** prevención focalizada → reducción potencial de victimización en los **municipios y periodos**
  proyectados; transparencia ciudadana con un asistente que responde con dato oficial citado.
- **Económico:** mejor asignación del gasto en seguridad (el costo de la inseguridad ronda el 3,64 % del
  PIB); evitar despliegues homogéneos ineficientes.
- **Institucional:** una base de evidencia común y **reproducible** (todo el pipeline regenera los datos)
  para Consejos de Seguridad, observatorios y rendición de cuentas.
- **Justicia (rendición de cuentas):** la capa Fiscalía expone el **embudo de judicialización** —solo
  **~8,5 %** de las noticias criminales superan la indagación a nivel nacional (5,6 % en Bogotá)—, un cuello
  de botella del sistema penal que ningún conteo de delitos revela; insumo de control social y de política de
  justicia, más allá de la prevención del delito.

> Estos efectos son el **mecanismo esperado** del instrumento; su **magnitud** real solo puede medirse con un
> piloto junto a una entidad (ver [docs/ADOPCION.md](ADOPCION.md)). VigIA aporta la base de evidencia, no una
> garantía de resultado.

---

## 6. Por qué es escalable

- **Costo marginal ~0 por territorio:** el modelo es global y *name-agnostic* (se indexa por código y
  categoría); añadir municipios o un departamento entero no exige reentrenar a mano ni reescribir código.
- **Datos 100 % abiertos y gratuitos** (datos.gov.co + DANE): cualquier entidad puede desplegarlo sin
  licencias de datos.
- **Despliegue reproducible** (Docker Compose, un comando) y **proveedor de IA conmutable** (local o
  gestionado) según la capacidad de cómputo de la entidad.

> La ruta concreta para que una entidad adopte y pilotee VigIA está en [docs/ADOPCION.md](ADOPCION.md).
