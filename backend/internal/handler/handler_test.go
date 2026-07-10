package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/vigia/backend/internal/config"
)

// El health responde 200 aunque no haya base de datos conectada.
func TestHealth(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
	rec := httptest.NewRecorder()

	h.Health(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("esperaba 200, obtuve %d", rec.Code)
	}
	var body map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("respuesta no es JSON: %v", err)
	}
	if body["status"] != "ok" {
		t.Fatalf("status inesperado: %v", body["status"])
	}
	if body["db"] != false {
		t.Fatalf("esperaba db=false sin repositorio, obtuve %v", body["db"])
	}
}

// Ready (readiness) sin BD alcanzable devuelve 503: así el HEALTHCHECK del contenedor marca
// "unhealthy" cuando la base está caída, en vez de mentir con un 200.
func TestReadyNoDB(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/ready", nil)
	rec := httptest.NewRecorder()

	h.Ready(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("esperaba 503 sin BD alcanzable, obtuve %d", rec.Code)
	}
}

// Summary sin base de datos devuelve 503 (no 500).
func TestSummaryNoDB(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/crimes/summary", nil)
	rec := httptest.NewRecorder()

	h.Summary(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("esperaba 503, obtuve %d", rec.Code)
	}
}

// MunicipioDetalle sin el parámetro cod_municipio devuelve 400 (no toca la BD).
func TestMunicipioDetalleRequiereCod(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/crimes/municipio", nil)
	rec := httptest.NewRecorder()

	h.MunicipioDetalle(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("esperaba 400 sin cod_municipio, obtuve %d", rec.Code)
	}
}

// JusticiaResumen sin base de datos devuelve 503 (no 500).
func TestJusticiaResumenNoDB(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/justicia/resumen", nil)
	rec := httptest.NewRecorder()

	h.JusticiaResumen(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("esperaba 503, obtuve %d", rec.Code)
	}
}

// JusticiaMunicipios sin base de datos devuelve 503 (no 500).
func TestJusticiaMunicipiosNoDB(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/justicia/municipios", nil)
	rec := httptest.NewRecorder()

	h.JusticiaMunicipios(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("esperaba 503, obtuve %d", rec.Code)
	}
}

// JusticiaDelitos sin base de datos devuelve 503 (no 500).
func TestJusticiaDelitosNoDB(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/justicia/delitos", nil)
	rec := httptest.NewRecorder()

	h.JusticiaDelitos(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("esperaba 503, obtuve %d", rec.Code)
	}
}

// JusticiaMunicipioDetalle sin el parámetro cod_municipio devuelve 400 (no toca la BD).
func TestJusticiaMunicipioDetalleRequiereCod(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/justicia/municipio", nil)
	rec := httptest.NewRecorder()

	h.JusticiaMunicipioDetalle(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("esperaba 400 sin cod_municipio, obtuve %d", rec.Code)
	}
}
