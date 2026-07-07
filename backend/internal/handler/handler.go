// Package handler implementa los manejadores HTTP de la API VigIA.
package handler

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/vigia/backend/internal/config"
	"github.com/vigia/backend/internal/mlclient"
	"github.com/vigia/backend/internal/realtime"
	"github.com/vigia/backend/internal/redisstore"
	"github.com/vigia/backend/internal/repository"
)

type Handler struct {
	repo                *repository.Repository
	ml                  *mlclient.Client
	store               *redisstore.Store
	news                newsSource
	cache               cacheConfig
	registrationEnabled bool
}

// newsSource abstrae la fuente de señales en tiempo real (GDELT) para poder inyectar un doble en
// los tests sin salir a la red.
type newsSource interface {
	Recent(ctx context.Context, depto string, max int) ([]realtime.Item, error)
}

// cacheConfig controla la caché en Redis de las respuestas de IA (pronóstico y asistente).
type cacheConfig struct {
	enabled      bool
	forecastTTL  time.Duration
	assistantTTL time.Duration
}

func New(repo *repository.Repository, ml *mlclient.Client, store *redisstore.Store, cfg config.Config) *Handler {
	// Fuente de señal en tiempo real: newsdata.io si hay API key (más fiable), si no GDELT (sin
	// token, reproducible). Ambas implementan newsSource.
	var news newsSource = realtime.NewClient()
	proveedor := "gdelt"
	if cfg.NewsDataAPIKey != "" {
		news = realtime.NewNewsDataClient(cfg.NewsDataAPIKey)
		proveedor = "newsdata.io"
	}
	slog.Info("fuente de señal en tiempo real", "proveedor", proveedor)

	return &Handler{
		repo:  repo,
		ml:    ml,
		store: store,
		news:  news,
		cache: cacheConfig{
			enabled:      cfg.CacheEnabled,
			forecastTTL:  cfg.CacheForecastTTL,
			assistantTTL: cfg.CacheAssistantTTL,
		},
		registrationEnabled: cfg.RegistrationEnabled,
	}
}

// cacheActive indica si se debe leer/escribir caché para esta petición (habilitada, con
// store disponible y sin el bypass `?nocache=1`).
func (h *Handler) cacheActive(r *http.Request) bool {
	return h.cache.enabled && h.store != nil && r.URL.Query().Get("nocache") != "1"
}

// writeRaw escribe una respuesta JSON cruda (bytes ya serializados) con cabecera X-Cache.
func writeRaw(w http.ResponseWriter, status int, data []byte, cacheState string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if cacheState != "" {
		w.Header().Set("X-Cache", cacheState)
	}
	w.WriteHeader(status)
	_, _ = w.Write(data)
}

// ── helpers ──
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

// writeMLResponse reenvía al cliente la respuesta del servicio ML. En éxito (2xx) reenvía el
// cuerpo JSON tal cual; ante error NO reenvía el cuerpo crudo del ML (puede contener detalles
// internos o trazas) sino un mensaje saneado, registrando el original para diagnóstico.
func writeMLResponse(w http.ResponseWriter, status int, data []byte, cacheState string) {
	if status >= 200 && status < 300 {
		writeRaw(w, status, data, cacheState)
		return
	}
	slog.Warn("error del servicio ML (cuerpo no reenviado al cliente)",
		"status", status, "cuerpo", string(data))
	msg := "el servicio de IA no pudo procesar la solicitud en este momento"
	if status == http.StatusServiceUnavailable {
		msg = "el servicio de IA no está disponible temporalmente"
	}
	writeError(w, status, msg)
}

func queryInt(r *http.Request, key string, def int) int {
	if v := r.URL.Query().Get(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func queryFloat(r *http.Request, key string, def float64) float64 {
	if v := r.URL.Query().Get(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

func clampInt(n, lo, hi int) int {
	if n < lo {
		return lo
	}
	if n > hi {
		return hi
	}
	return n
}

func clampFloat(f, lo, hi float64) float64 {
	if f < lo {
		return lo
	}
	if f > hi {
		return hi
	}
	return f
}

// ── endpoints ──

// dbReachable comprueba la conectividad REAL con la BD con un tope de tiempo corto, para que
// las sondas no queden colgadas si la base no responde.
func (h *Handler) dbReachable(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	return h.repo.Ping(ctx) == nil
}

// Health es la sonda de LIVENESS: 200 mientras el proceso responda. El campo `db` refleja la
// conectividad REAL (ping), no solo que exista el pool, para que el tablero no muestre "BD OK"
// cuando la base está caída. No condiciona el 200 a la BD: reiniciar el contenedor no arregla
// una BD externa caída (evita bucles de reinicio); para eso está la sonda de readiness.
func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok",
		"db":     h.dbReachable(r.Context()),
	})
}

// Ready es la sonda de READINESS: 200 solo si la BD es alcanzable; 503 si no. La usa el
// HEALTHCHECK del contenedor, de modo que el orquestador marca "unhealthy" cuando la base está
// caída (y NO cuando solo está sin poblar: el ping igual responde). Así el healthcheck deja de
// mentir (antes daba 200 con todos los datos en 503).
func (h *Handler) Ready(w http.ResponseWriter, r *http.Request) {
	if h.dbReachable(r.Context()) {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ready", "db": true})
		return
	}
	writeJSON(w, http.StatusServiceUnavailable, map[string]any{
		"status": "degraded",
		"db":     false,
		"reason": "base de datos no accesible",
	})
}

// Config expone la configuración pública que el frontend necesita al arrancar: feature flags
// resueltos por el servidor en tiempo de ejecución (no en build). Hoy: si el registro de
// cuentas ciudadanas está habilitado.
func (h *Handler) Config(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"registration_enabled": h.registrationEnabled,
	})
}

// RealtimeDepartamento devuelve una SEÑAL EN TIEMPO REAL de prensa (GDELT) para un departamento (o
// nacional si no se pasa `cod`). Es un complemento —no sustituto— del dato oficial mensual: son
// NOTICIAS, no cifras. Público. La caché en Redis (20 min éxito / 90 s degradado) es imprescindible
// porque GDELT rate-limita con dureza; ante fallo/rate-limit degrada a "señal no disponible" (200).
func (h *Handler) RealtimeDepartamento(w http.ResponseWriter, r *http.Request) {
	depto := "Nacional"
	deptQuery := "" // vacío = consulta nacional
	cod := r.URL.Query().Get("cod")
	if cod != "" {
		name, ok := realtime.DepartamentoNombre(cod)
		if !ok {
			writeError(w, http.StatusBadRequest, "código de departamento inválido")
			return
		}
		depto, deptQuery = name, name
	}

	cacheKey := "cache:realtime:" + depto
	if h.store != nil {
		if cached, ok := h.store.GetCached(r.Context(), cacheKey); ok {
			writeRaw(w, http.StatusOK, cached, "HIT")
			return
		}
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	items, err := h.news.Recent(ctx, deptQuery, 12)

	resp := map[string]any{
		"cod":          cod,
		"departamento": depto,
		"fuente":       "Prensa (señal en tiempo real) — no son cifras oficiales",
		"items":        items,
	}
	ttl := 20 * time.Minute
	if err != nil {
		slog.Warn("señal en tiempo real no disponible", "departamento", depto, "error", err)
		resp["items"] = []realtime.Item{}
		resp["nota"] = "Señal no disponible en este momento."
		ttl = 90 * time.Second // caché negativa corta: no martillar GDELT ante fallos/rate-limit
	}
	body, _ := json.Marshal(resp)
	if h.store != nil {
		h.store.SetCached(r.Context(), cacheKey, body, ttl)
	}
	writeRaw(w, http.StatusOK, body, "MISS")
}

// Summary devuelve los municipios con mayor incidencia.
func (h *Handler) Summary(w http.ResponseWriter, r *http.Request) {
	limit := clampInt(queryInt(r, "limit", 20), 1, 5000)
	data, err := h.repo.TopMunicipios(r.Context(), limit)
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// Municipios devuelve todos los municipios (orden alfabético) para los selectores.
func (h *Handler) Municipios(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.Municipios(r.Context())
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// Stats devuelve los totales globales del tablero (para tarjetas KPI).
func (h *Handler) Stats(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.GetStats(r.Context())
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// Departamentos devuelve la incidencia agregada por departamento (mapa de calor).
func (h *Handler) Departamentos(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.Departamentos(r.Context())
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// Categories devuelve las categorías de delito disponibles. Acepta `cod_municipio`
// opcional para limitar a las categorías con datos en ese municipio.
func (h *Handler) Categories(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.Categorias(r.Context(), r.URL.Query().Get("cod_municipio"))
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// MunicipioDetalle devuelve el desglose por categoría de un municipio (para el drill-down).
func (h *Handler) MunicipioDetalle(w http.ResponseWriter, r *http.Request) {
	cod := r.URL.Query().Get("cod_municipio")
	if cod == "" {
		writeError(w, http.StatusBadRequest, "parámetro requerido: cod_municipio")
		return
	}
	data, err := h.repo.MunicipioDetalle(r.Context(), cod)
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// TimeSeries devuelve la serie mensual de un municipio/categoría.
func (h *Handler) TimeSeries(w http.ResponseWriter, r *http.Request) {
	cod := r.URL.Query().Get("cod_municipio")
	cat := r.URL.Query().Get("categoria")
	if cod == "" || cat == "" {
		writeError(w, http.StatusBadRequest, "parámetros requeridos: cod_municipio, categoria")
		return
	}
	data, err := h.repo.TimeSeries(r.Context(), cod, cat)
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// Anomalies devuelve una página de alertas tempranas (paginación de servidor).
// El total que cumple el filtro se expone en la cabecera X-Total-Count.
func (h *Handler) Anomalies(w http.ResponseWriter, r *http.Request) {
	q := repository.AnomaliaQuery{
		Limit:     clampInt(queryInt(r, "limit", 50), 1, 200),
		Offset:    clampInt(queryInt(r, "offset", 0), 0, 1_000_000),
		Severidad: r.URL.Query().Get("severidad"),
		Search:    r.URL.Query().Get("q"),
		Sort:      r.URL.Query().Get("sort"),
		Dir:       r.URL.Query().Get("dir"),
	}
	data, total, err := h.repo.Anomalias(r.Context(), q)
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	w.Header().Set("X-Total-Count", strconv.Itoa(total))
	writeJSON(w, http.StatusOK, data)
}

// Forecast reenvía la petición de pronóstico al servicio ML.
func (h *Handler) Forecast(w http.ResponseWriter, r *http.Request) {
	cod := r.URL.Query().Get("cod_municipio")
	cat := r.URL.Query().Get("categoria")
	if cod == "" || cat == "" {
		writeError(w, http.StatusBadRequest, "parámetros requeridos: cod_municipio, categoria")
		return
	}
	// Acota el horizonte [1, 24] meses: evita un cómputo desbocado en el ML y claves de caché
	// absurdas por un valor arbitrario del cliente (el horizonte por defecto es 6; el monitoreo llega a 12).
	horizon := clampInt(queryInt(r, "horizon", 6), 1, 24)

	// Caché: el pronóstico es determinista por (municipio, categoría, horizonte) y solo
	// cambia al reentrenar el modelo. Responde las consultas repetidas en ms en vez de golpear
	// al servicio ML cada vez (que en CPU es lento).
	key := fmt.Sprintf("cache:forecast:%s:%s:%d", cod, cat, horizon)
	if h.cacheActive(r) {
		if cached, ok := h.store.GetCached(r.Context(), key); ok {
			writeRaw(w, http.StatusOK, cached, "HIT")
			return
		}
	}

	payload := map[string]any{
		"cod_municipio": cod,
		"categoria":     cat,
		"horizon":       horizon,
	}
	data, status, err := h.ml.Proxy(r.Context(), http.MethodPost, "/predict", payload)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	if status == http.StatusOK && h.cacheActive(r) {
		h.store.SetCached(r.Context(), key, data, h.cache.forecastTTL)
	}
	writeMLResponse(w, status, data, "MISS")
}

// Simulate reenvía una simulación de escenario "¿y si…?" al servicio ML. Proyecta una
// intervención (supuesto del usuario) y/o un shock de población (palanca del modelo) sobre el
// pronóstico base y devuelve los hechos evitados acumulados.
func (h *Handler) Simulate(w http.ResponseWriter, r *http.Request) {
	cod := r.URL.Query().Get("cod_municipio")
	cat := r.URL.Query().Get("categoria")
	if cod == "" || cat == "" {
		writeError(w, http.StatusBadRequest, "parámetros requeridos: cod_municipio, categoria")
		return
	}
	// Acota horizonte y palancas a rangos razonables (evita DoS del ML y claves de caché
	// desbocadas). intervencion_pct es un supuesto del usuario; shock_poblacion_pct una palanca
	// del modelo. Los topes son generosos pero finitos.
	horizon := clampInt(queryInt(r, "horizon", 6), 1, 24)
	intervencion := clampFloat(queryFloat(r, "intervencion_pct", 0), -100, 100)
	ramp := clampInt(queryInt(r, "ramp_meses", 0), 0, 24)
	shockPob := clampFloat(queryFloat(r, "shock_poblacion_pct", 0), -90, 1000)

	// Caché: la simulación es determinista por (municipio, categoría, horizonte, palancas) y solo
	// cambia al reentrenar el modelo. Reutiliza el TTL del pronóstico (es una variante de él).
	key := fmt.Sprintf("cache:simulate:%s:%s:%d:%g:%d:%g",
		cod, cat, horizon, intervencion, ramp, shockPob)
	if h.cacheActive(r) {
		if cached, ok := h.store.GetCached(r.Context(), key); ok {
			writeRaw(w, http.StatusOK, cached, "HIT")
			return
		}
	}

	payload := map[string]any{
		"cod_municipio":       cod,
		"categoria":           cat,
		"horizon":             horizon,
		"intervencion_pct":    intervencion,
		"ramp_meses":          ramp,
		"shock_poblacion_pct": shockPob,
	}
	data, status, err := h.ml.Proxy(r.Context(), http.MethodPost, "/simulate", payload)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	if status == http.StatusOK && h.cacheActive(r) {
		h.store.SetCached(r.Context(), key, data, h.cache.forecastTTL)
	}
	writeMLResponse(w, status, data, "MISS")
}

// Monitoring reenvía el reporte de salud del modelo (frescura, deriva, backtest extendido)
// del servicio ML. Lectura barata (un JSON) → pública como el resto de agregados.
func (h *Handler) Monitoring(w http.ResponseWriter, r *http.Request) {
	data, status, err := h.ml.Proxy(r.Context(), http.MethodGet, "/monitoring", nil)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeMLResponse(w, status, data, "")
}

// Brief reenvía el informe ejecutivo de seguridad de un municipio (IA generativa) del servicio
// ML. Es cómputo de LLM (caro) → protegido con JWT y cacheado por municipio (se invalida al
// reentrenar/repipeline; usa `?nocache=1` para forzar). El cod_municipio se valida numérico
// antes de construir la ruta del ML (evita inyección en el path).
func (h *Handler) Brief(w http.ResponseWriter, r *http.Request) {
	cod := r.URL.Query().Get("cod_municipio")
	if cod == "" {
		writeError(w, http.StatusBadRequest, "parámetro requerido: cod_municipio")
		return
	}
	for _, c := range cod {
		if c < '0' || c > '9' {
			writeError(w, http.StatusBadRequest, "cod_municipio debe ser numérico")
			return
		}
	}

	key := "cache:brief:" + cod
	if h.cacheActive(r) {
		if cached, ok := h.store.GetCached(r.Context(), key); ok {
			writeRaw(w, http.StatusOK, cached, "HIT")
			return
		}
	}

	data, status, err := h.ml.Proxy(r.Context(), http.MethodGet, "/brief/"+cod, nil)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	if status == http.StatusOK && h.cacheActive(r) {
		h.store.SetCached(r.Context(), key, data, h.cache.forecastTTL)
	}
	writeMLResponse(w, status, data, "MISS")
}

// Assistant reenvía la consulta del ciudadano al RAG del servicio ML.
func (h *Handler) Assistant(w http.ResponseWriter, r *http.Request) {
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		writeError(w, http.StatusBadRequest, "no se pudo leer el cuerpo")
		return
	}
	var body map[string]any
	if err := json.Unmarshal(raw, &body); err != nil {
		writeError(w, http.StatusBadRequest, "JSON inválido")
		return
	}

	// Clave de caché por la pregunta normalizada (el LLM corre con temperatura baja, así
	// que preguntas idénticas dan respuestas equivalentes). Se hashea para no usar texto
	// libre como clave. Si no hay pregunta utilizable, se omite la caché (no se altera el
	// comportamiento: se reenvía el cuerpo tal cual).
	key := ""
	if p, ok := body["pregunta"].(string); ok && strings.TrimSpace(p) != "" {
		sum := sha256.Sum256([]byte(strings.ToLower(strings.TrimSpace(p))))
		key = "cache:rag:" + hex.EncodeToString(sum[:])
	}
	if key != "" && h.cacheActive(r) {
		if cached, ok := h.store.GetCached(r.Context(), key); ok {
			writeRaw(w, http.StatusOK, cached, "HIT")
			return
		}
	}

	data, status, err := h.ml.Proxy(r.Context(), http.MethodPost, "/rag/chat", body)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	if status == http.StatusOK && key != "" && h.cacheActive(r) {
		h.store.SetCached(r.Context(), key, data, h.cache.assistantTTL)
	}
	writeMLResponse(w, status, data, "MISS")
}

func statusForRepoErr(w http.ResponseWriter, err error) {
	if errors.Is(err, repository.ErrNoDB) || errors.Is(err, repository.ErrNotInitialized) {
		writeError(w, http.StatusServiceUnavailable,
			"datos no disponibles: ejecuta el pipeline (make docker-pipeline)")
		return
	}
	writeError(w, http.StatusInternalServerError, err.Error())
}

// ───────────────────────── Capa "Justicia" (Fiscalía) ─────────────────────────

// JusticiaResumen devuelve el embudo nacional de judicialización + KPIs.
func (h *Handler) JusticiaResumen(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.JusticiaResumen(r.Context())
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// JusticiaMunicipios devuelve el ranking de municipios por procesos/tasa de judicialización.
func (h *Handler) JusticiaMunicipios(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.JusticiaMunicipios(r.Context())
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// JusticiaDepartamentos devuelve la tasa de judicialización agregada por departamento (coropleta).
func (h *Handler) JusticiaDepartamentos(w http.ResponseWriter, r *http.Request) {
	data, err := h.repo.JusticiaDepartamentos(r.Context())
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}

// JusticiaMunicipioDetalle devuelve el desglose año×etapa de un municipio (drill-down).
func (h *Handler) JusticiaMunicipioDetalle(w http.ResponseWriter, r *http.Request) {
	cod := r.URL.Query().Get("cod_municipio")
	if cod == "" {
		writeError(w, http.StatusBadRequest, "parámetro requerido: cod_municipio")
		return
	}
	data, err := h.repo.JusticiaMunicipioDetalle(r.Context(), cod)
	if err != nil {
		statusForRepoErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, data)
}
