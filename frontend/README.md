# Frontend React — Tablero VigIA

Tablero interactivo (React 18 + TypeScript + Vite) con ocho vistas. **Panorama**, **Alertas**,
**Justicia** y **Salud del modelo** son públicas; **Pronóstico**, **Simulador**, **Asistente** e
**Informe** requieren inicio de sesión (cómputo de IA protegido, `<AuthGate>`):

- **Panorama** — KPIs nacionales, ranking de municipios, gráfico de barras y mapa coroplético por
  departamento (Leaflet); desglose por municipio y panel de **señales de prensa** recientes
  (clic en un departamento carga sus noticias de seguridad; complemento, no cifra oficial).
- **Alertas tempranas** — tabla de anomalías detectadas por severidad, con búsqueda y filtros.
- **Justicia** — embudo de judicialización de la Fiscalía (KPIs, etapas, barras por departamento y tabla).
- **Pronóstico** *(JWT)* — histórico + pronóstico a 6 meses por municipio y categoría, con banda de
  incertidumbre (Recharts).
- **Simulador** *(JWT)* — palancas de intervención/población con base vs. escenario y hechos evitados.
- **Asistente ciudadano** *(JWT)* — chat RAG/agente sobre datos oficiales, con fuentes citadas.
- **Informe** *(JWT)* — informe ejecutivo municipal generado por IA (panorama, alertas, pronóstico,
  judicialización) anclado a las cifras oficiales.
- **Salud del modelo** — semáforo de frescura, deriva (PSI) y validación retrospectiva (*backtest*) a 12 meses.

## Desarrollo

```bash
npm install
npm run dev        # http://localhost:5173
```

La URL de la API se configura con `VITE_API_BASE_URL` (por defecto `http://localhost:8080/api/v1`).

## Build de producción

```bash
npm run build      # genera dist/ (lo publica nginx en el contenedor)
```
