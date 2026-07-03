package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/vigia/backend/internal/config"
	"github.com/vigia/backend/internal/realtime"
)

// stubNews implementa newsSource sin salir a la red.
type stubNews struct {
	items []realtime.Item
	err   error
}

func (s stubNews) Recent(context.Context, string, int) ([]realtime.Item, error) {
	return s.items, s.err
}

func TestRealtimeInvalidCod(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/realtime/departamento?cod=00", nil)
	rec := httptest.NewRecorder()

	h.RealtimeDepartamento(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("un cod inválido debería dar 400, obtuve %d", rec.Code)
	}
}

func TestRealtimeNationalStub(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	h.news = stubNews{items: []realtime.Item{{Titulo: "t", URL: "http://x", Fuente: "x.com", Fecha: "2026-01-15"}}}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/realtime/departamento", nil)
	rec := httptest.NewRecorder()

	h.RealtimeDepartamento(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("esperaba 200, obtuve %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"departamento":"Nacional"`) {
		t.Fatalf("cuerpo inesperado: %s", rec.Body.String())
	}
}

func TestRealtimeDegradesOnError(t *testing.T) {
	h := New(nil, nil, nil, config.Config{})
	h.news = stubNews{err: context.DeadlineExceeded}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/realtime/departamento?cod=05", nil)
	rec := httptest.NewRecorder()

	h.RealtimeDepartamento(rec, req)

	// Degrada con elegancia: 200 con nota, no un 5xx que rompa el panel público.
	if rec.Code != http.StatusOK {
		t.Fatalf("ante fallo de GDELT debería degradar a 200, obtuve %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "no disponible") {
		t.Fatalf("esperaba la nota de 'no disponible': %s", rec.Body.String())
	}
}
