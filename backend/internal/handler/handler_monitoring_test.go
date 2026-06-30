package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// Monitoring reenvía el reporte de salud del servicio ML (200 con el cuerpo del ML).
func TestMonitoringProxy(t *testing.T) {
	var hits int32
	h := newCacheHandler(t, &hits)

	rec := httptest.NewRecorder()
	h.Monitoring(rec, httptest.NewRequest(http.MethodGet, "/api/v1/monitoring", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("esperaba 200, obtuve %d", rec.Code)
	}
	if rec.Body.String() != `{"ok":true}` {
		t.Fatalf("cuerpo del ML no reenviado: %q", rec.Body.String())
	}
}
