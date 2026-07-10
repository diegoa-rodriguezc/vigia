# Backend Go — API REST de VigIA

API REST / *Backend for Frontend* (BFF) que expone los datos gold (PostgreSQL) y hace de proxy hacia
el servicio ML de Python (pronósticos y asistente RAG).

## Estructura

```
backend/
├── cmd/api/main.go              # arranque y apagado ordenado
└── internal/
    ├── config/                  # configuración por variables de entorno
    ├── server/                  # router chi + middlewares + CORS
    ├── handler/                 # manejadores HTTP
    ├── auth/                    # JWT, servicio de sesión y middleware de autenticación
    ├── middleware/              # rate-limiting y utilidades HTTP
    ├── repository/              # acceso a PostgreSQL (pgx)
    ├── redisstore/              # sesiones, denylist y caché de IA en Redis
    └── mlclient/                # cliente del servicio ML (Python)
```

## Endpoints (`/api/v1`)

Los endpoints de lectura son **públicos** (con *rate-limiting* por IP); los de cómputo de IA caro
exigen **JWT** (`Authorization: Bearer`).

| Método | Ruta | Acceso | Origen | Descripción |
|---|---|---|---|---|
| GET | `/health` | público | — | Estado del backend |
| POST | `/auth/login` · `/auth/refresh` | público (rate-limit) | — | Login y rotación de tokens |
| POST/GET | `/auth/logout` · `/auth/me` | **JWT** | — | Logout (denylist) e identidad |
| GET | `/crimes/summary` | público | PostgreSQL | Municipios con mayor incidencia |
| GET | `/crimes/stats` | público | PostgreSQL | Totales reales (COUNT/SUM) para KPIs |
| GET | `/crimes/municipios` · `/crimes/departamentos` · `/crimes/categories` | público | PostgreSQL | Rankings y agregados (mapa coroplético) |
| GET | `/crimes/municipio` | público | PostgreSQL | Desglose por categoría (drill-down) |
| GET | `/crimes/timeseries` | público | PostgreSQL | Serie mensual |
| GET | `/anomalies` | público | PostgreSQL | Alertas tempranas detectadas |
| GET | `/monitoring` | público | Proxy ML | Salud del modelo (frescura, PSI, backtest 12m) |
| GET | `/justicia/resumen` · `/justicia/municipios` · `/justicia/departamentos` · `/justicia/municipio` | público | PostgreSQL | Embudo de judicialización (Fiscalía) |
| GET | `/forecast` | **JWT** | Proxy ML | Pronóstico |
| GET | `/simulate` | **JWT** | Proxy ML | Simulación de escenarios (palancas en query) |
| POST | `/assistant` | **JWT** | Proxy ML | Asistente ciudadano (RAG/agente) |
| GET | `/brief?cod_municipio=` | **JWT** | Proxy ML | Informe ejecutivo municipal (IA generativa) |

## Desarrollo

```bash
go run ./cmd/api        # requiere DATABASE_URL y ML_API_URL (ver .env)
go test ./...
```

El backend arranca aunque la base de datos aún no tenga datos: los endpoints de datos responden
`503` con mensaje accionable hasta que el pipeline (`make docker-pipeline`) cargue las tablas gold.
