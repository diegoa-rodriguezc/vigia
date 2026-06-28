// Package handler implementa los manejadores HTTP de la API VigIA.
package handler

import (
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
	"github.com/vigia/backend/internal/redisstore"
	"github.com/vigia/backend/internal/repository"
)

type Handler struct {
	repo  *repository.Repository
	ml    *mlclient.Client
	store *redisstore.Store
	cache cacheConfig
}

// cacheConfig controla la caché en Redis de las respuestas de IA (pronóstico y asistente).
type cacheConfig struct {
	enabled      bool
	forecastTTL  time.Duration
	assistantTTL time.Duration
}

func New(repo *repository.Repository, ml *mlclient.Client, store *redisstore.Store, cfg config.Config) *Handler {
	return &Handler{
		repo:  repo,
		ml:    ml,
		store: store,
		cache: cacheConfig{
			enabled:      cfg.CacheEnabled,
			forecastTTL:  cfg.CacheForecastTTL,
			assistantTTL: cfg.CacheAssistantTTL,
		},
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

// ── endpoints ──

// Health reporta el estado del backend.
func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok",
		"db":     h.repo.Available(),
	})
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
	horizon := queryInt(r, "horizon", 6)

	// Caché: el pronóstico es determinista por (municipio, categoría, horizonte) y solo
	// cambia al reentrenar el modelo. Sirve respuestas repetidas en ms en vez de golpear
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
	horizon := queryInt(r, "horizon", 6)
	intervencion := queryFloat(r, "intervencion_pct", 0)
	ramp := queryInt(r, "ramp_meses", 0)
	shockPob := queryFloat(r, "shock_poblacion_pct", 0)

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

// Monitoring proxya el reporte de salud del modelo (frescura, deriva, backtest extendido)
// del servicio ML. Lectura barata (un JSON) → pública como el resto de agregados.
func (h *Handler) Monitoring(w http.ResponseWriter, r *http.Request) {
	data, status, err := h.ml.Proxy(r.Context(), http.MethodGet, "/monitoring", nil)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeMLResponse(w, status, data, "")
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
