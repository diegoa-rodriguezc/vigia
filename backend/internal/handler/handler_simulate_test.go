package handler

import (
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/vigia/backend/internal/config"
)

// Simulate sin los parámetros requeridos devuelve 400.
func TestSimulateRequiereParametros(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/simulate?cod_municipio=11001", nil)
	rec := httptest.NewRecorder()

	h.Simulate(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("esperaba 400 sin categoria, obtuve %d", rec.Code)
	}
}

// La caché de simulación distingue por palancas: cambiar una palanca es MISS (no sirve el
// resultado de otro escenario), y repetir el mismo escenario es HIT.
func TestSimulateCachePorPalancas(t *testing.T) {
	var hits int32
	h := newCacheHandler(t, &hits)
	base := "/api/v1/simulate?cod_municipio=11001&categoria=HOMICIDIO&intervencion_pct=-15"

	rec1 := httptest.NewRecorder()
	h.Simulate(rec1, httptest.NewRequest(http.MethodGet, base, nil))
	if rec1.Code != http.StatusOK || rec1.Header().Get("X-Cache") != "MISS" {
		t.Fatalf("1ª: esperaba 200 MISS, obtuve %d %q", rec1.Code, rec1.Header().Get("X-Cache"))
	}

	// Mismo escenario → HIT (no golpea al ML).
	rec2 := httptest.NewRecorder()
	h.Simulate(rec2, httptest.NewRequest(http.MethodGet, base, nil))
	if rec2.Header().Get("X-Cache") != "HIT" {
		t.Fatalf("2ª: esperaba HIT, obtuve %q", rec2.Header().Get("X-Cache"))
	}

	// Distinta palanca de intervención → MISS (escenario diferente, no reusa la caché).
	rec3 := httptest.NewRecorder()
	h.Simulate(rec3, httptest.NewRequest(http.MethodGet, base+"0", nil)) // -150 ≠ -15
	if rec3.Header().Get("X-Cache") != "MISS" {
		t.Fatalf("3ª: esperaba MISS con otra palanca, obtuve %q", rec3.Header().Get("X-Cache"))
	}

	if got := atomic.LoadInt32(&hits); got != 2 {
		t.Fatalf("el ML debió llamarse 2 veces (2 escenarios distintos), fueron %d", got)
	}
}
