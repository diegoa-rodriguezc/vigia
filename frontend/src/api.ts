import axios from "axios";
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from "./auth/tokens";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080/api/v1";

// Timeout amplio: la latencia del asistente RAG depende del proveedor de LLM — con el
// modelo local (Ollama en CPU) una consulta puede tardar ~30-90s; con proveedor gestionado
// responde en segundos. El resto de endpoints responde en milisegundos.
export const api = axios.create({ baseURL, timeout: 240_000 });

// Instancia "cruda" SIN interceptores, usada para renovar el token (evita recursión
// cuando /auth/refresh también respondiera 401).
const rawApi = axios.create({ baseURL, timeout: 30_000 });

// Adjunta el access token a cada petición si existe.
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Renovación de token con deduplicación: si varias peticiones reciben 401 a la vez,
// solo se dispara UN refresh y todas esperan su resultado.
let refreshing: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  const rt = getRefreshToken();
  if (!rt) return null;
  try {
    const r = await rawApi.post("/auth/refresh", { refresh_token: rt });
    setTokens(r.data.access_token, r.data.refresh_token);
    return r.data.access_token as string;
  } catch {
    clearTokens(); // refresh inválido/expirado → cerrar sesión
    return null;
  }
}

// Ante un 401 en un endpoint protegido, intenta renovar UNA vez y reintenta la petición.
api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    if (status === 401 && original && !original._retry && getRefreshToken()) {
      original._retry = true;
      refreshing = refreshing ?? refreshAccess();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

// ── Autenticación ──
export interface AuthUser { id: string; username: string; role: string }
interface LoginResult { access_token: string; refresh_token: string; user: AuthUser }

export async function login(username: string, password: string): Promise<AuthUser> {
  const r = await rawApi.post<LoginResult>("/auth/login", { username, password });
  setTokens(r.data.access_token, r.data.refresh_token);
  return r.data.user;
}

export async function logout(): Promise<void> {
  const refresh_token = getRefreshToken();
  try {
    await api.post("/auth/logout", { refresh_token });
  } catch {
    /* el logout es best-effort: aunque falle en el servidor, limpiamos local */
  }
  clearTokens();
}

export const getMe = () => api.get<AuthUser>("/auth/me").then((r) => r.data);

// ── Tipos de dominio ──
export interface MunicipioResumen {
  cod_municipio: string;
  municipio: string;
  departamento: string;
  total_hechos: number;       // gran total (delitos + respuestas)
  total_delitos: number;      // incidencia delictiva
  total_respuestas: number;   // capturas / incautaciones / recuperaciones
  categorias: number;
  lat: number | null;
  lon: number | null;
}

export interface SeriePunto {
  periodo: string;
  cantidad: number;
}

export interface Anomalia {
  cod_municipio: string;
  municipio: string;
  departamento: string;
  categoria: string;
  periodo: string;
  cantidad: number;
  score_z: number;
  severidad: string;
}

export interface ForecastPoint {
  periodo: string;
  prediccion: number;
  limite_inferior?: number | null;
  limite_superior?: number | null;
}

export interface ForecastResponse {
  cod_municipio: string;
  categoria: string;
  horizonte: number;
  pronostico: ForecastPoint[];
}

export interface SimulateDelta {
  periodo: string;
  base: number;
  escenario: number;
  evitados: number;
  evitados_acumulado: number;
}

export interface SimulateResponse {
  cod_municipio: string;
  categoria: string;
  horizonte: number;
  escenario: { intervencion_pct: number; ramp_meses: number; shock_poblacion_pct: number };
  base: ForecastPoint[];
  proyeccion: ForecastPoint[];
  delta: SimulateDelta[];
  evitados_total: number;
  nota: string;
}

export interface Fuente {
  content: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface ChatResponse {
  respuesta: string;
  fuentes: Fuente[];
}

// ── Llamadas ──
export interface Health { status: string; db: boolean }
export const getHealth = () => api.get<Health>("/health").then((r) => r.data);

export interface Stats {
  municipios: number;
  departamentos: number;
  categorias: number;
  total_hechos: number;
  total_delitos: number;
  total_respuestas: number;
  anomalias: number;
  anomalias_alta: number;
  anomalias_media: number;
  periodo_min: string;
  periodo_max: string;
}
// Totales reales del tablero (COUNT/SUM en BD, no limitados por paginación).
export const getStats = () => api.get<Stats>("/crimes/stats").then((r) => r.data);

export const getSummary = (limit = 20) =>
  api.get<MunicipioResumen[]>("/crimes/summary", { params: { limit } }).then((r) => r.data);

export interface MunicipioRef {
  cod_municipio: string;
  municipio: string;
  departamento: string;
}

// Todos los municipios (orden alfabético) para los selectores.
export const getMunicipios = () =>
  api.get<MunicipioRef[]>("/crimes/municipios").then((r) => r.data);

export interface DepartamentoResumen {
  cod_departamento: string;
  departamento: string;
  total_delitos: number;   // incidencia delictiva (no el gran total)
  municipios: number;
}

// Incidencia agregada por departamento (para el mapa de calor / coropleta).
export const getDepartamentos = () =>
  api.get<DepartamentoResumen[]>("/crimes/departamentos").then((r) => r.data);

// Sin municipio: todas las categorías. Con municipio: solo las que tienen datos ahí
// (evita combinaciones municipio×categoría sin historial que darían 404 al pronosticar).
export const getCategories = (cod_municipio?: string) =>
  api
    .get<string[]>("/crimes/categories", { params: cod_municipio ? { cod_municipio } : {} })
    .then((r) => r.data);

export const getTimeSeries = (cod_municipio: string, categoria: string) =>
  api
    .get<SeriePunto[]>("/crimes/timeseries", { params: { cod_municipio, categoria } })
    .then((r) => r.data);

export interface CategoriaTotal {
  categoria: string;
  naturaleza: string; // "delito" | "respuesta"
  total: number;
}

// Desglose por categoría de un municipio (para el drill-down del Panorama).
export const getMunicipioDetalle = (cod_municipio: string) =>
  api
    .get<CategoriaTotal[]>("/crimes/municipio", { params: { cod_municipio } })
    .then((r) => r.data);

export interface AnomaliasParams {
  limit?: number;
  offset?: number;
  severidad?: string;   // "ALTA" | "MEDIA"
  q?: string;           // texto libre
  sort?: string;        // columna
  dir?: "asc" | "desc";
}
export interface AnomaliasPage { items: Anomalia[]; total: number }

// Paginación de servidor: el total filtrado llega en la cabecera X-Total-Count.
export const getAnomalies = (params: AnomaliasParams = {}): Promise<AnomaliasPage> =>
  api.get<Anomalia[]>("/anomalies", { params }).then((r) => ({
    items: r.data,
    total: Number(r.headers["x-total-count"] ?? r.data.length),
  }));

export const getForecast = (cod_municipio: string, categoria: string, horizon = 6) =>
  api
    .get<ForecastResponse>("/forecast", { params: { cod_municipio, categoria, horizon } })
    .then((r) => r.data);

export interface SimulateParams {
  cod_municipio: string;
  categoria: string;
  horizon?: number;
  intervencion_pct?: number;   // % de cambio esperado de la incidencia (negativo = reducción)
  ramp_meses?: number;         // meses hasta el efecto pleno de la intervención
  shock_poblacion_pct?: number; // % de cambio de la población (palanca del modelo)
}

// Simulación de escenarios "¿y si…?" (endpoint de IA, requiere sesión como el pronóstico).
export const getSimulate = (params: SimulateParams) =>
  api.get<SimulateResponse>("/simulate", { params }).then((r) => r.data);

// ── Salud del modelo (monitoreo) ──
export type Estado = "verde" | "amarillo" | "rojo";

export interface Freshness { periodo_max: string | null; lag_meses: number | null; estado: Estado }
export interface DataDrift {
  psi: number;
  estado: Estado;
  ventana_meses: number;
  volumen_mensual_referencia?: number;
  volumen_mensual_reciente?: number;
  cambio_volumen_pct?: number | null;
  nota?: string;
}
export interface BacktestStep {
  paso: number;
  mae: number;
  smape: number;
  baseline_mae: number;
  baseline_smape: number;
  n: number;
}
export interface BacktestExt {
  horizon: number;
  n_origins: number;
  mae: number;
  baseline_mae: number;
  supera_baseline_mae: boolean;
  por_paso: BacktestStep[];
  estado: Estado;
}
export interface ModelHealth {
  generado_en: string;
  estado_global: Estado;
  frescura: Freshness;
  deriva_datos: DataDrift;
  backtest_extendido: BacktestExt | null;
}

export const getMonitoring = () => api.get<ModelHealth>("/monitoring").then((r) => r.data);

export const askAssistant = (pregunta: string) =>
  api.post<ChatResponse>("/assistant", { pregunta }).then((r) => r.data);

// ── Informe de seguridad municipal (IA generativa anclada a datos) ──
export interface BriefDatos {
  panorama: {
    total_delitos: number;
    total_respuestas: number;
    periodo: string;
    top_delitos: { categoria: string; total: number }[];
  };
  justicia?: {
    tasa_judicializacion_pct: number;
    total_procesos: number;
    n_judicializados: number;
  } | null;
}
export interface BriefResponse {
  cod_municipio: string;
  municipio: string;
  departamento: string;
  generado: string;   // fecha ISO de generación
  informe: string;    // texto del informe ejecutivo
  datos: BriefDatos;  // cifras ancladas que lo sustentan (auditable)
}

// Informe ejecutivo por municipio (endpoint de IA, requiere sesión). El LLM puede tardar
// (Ollama en CPU ~30-90 s); usa el timeout amplio de `api`.
export const getBrief = (cod_municipio: string) =>
  api.get<BriefResponse>("/brief", { params: { cod_municipio } }).then((r) => r.data);

// ── Capa "Justicia" (Fiscalía): embudo de judicialización ──
export interface JusticiaEtapa {
  etapa: string;
  clase_etapa: string; // indagacion | judicializado | desconocido
  n_procesos: number;
}
export interface JusticiaResumenNacional {
  total_procesos: number;
  total_judicializados: number;
  total_etapa_conocida: number;
  tasa_judicializacion_pct: number;
  municipios: number;
  embudo: JusticiaEtapa[];
}
export interface JusticiaMunicipio {
  cod_municipio: string;
  municipio: string;
  departamento: string;
  total_procesos: number;
  n_judicializados: number;
  tasa_judicializacion_pct: number;
}
export interface JusticiaDepartamento {
  cod_departamento: string;
  departamento: string;
  total_procesos: number;
  n_judicializados: number;
  tasa_judicializacion_pct: number;
  municipios: number;
}

export const getJusticiaResumen = () =>
  api.get<JusticiaResumenNacional>("/justicia/resumen").then((r) => r.data);
export const getJusticiaMunicipios = () =>
  api.get<JusticiaMunicipio[]>("/justicia/municipios").then((r) => r.data);
export const getJusticiaDepartamentos = () =>
  api.get<JusticiaDepartamento[]>("/justicia/departamentos").then((r) => r.data);
