package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// Con el registro deshabilitado, POST /auth/register se rechaza con 403 ANTES de tocar el
// servicio (la guarda corta al inicio), por eso el servicio puede ser nil en esta prueba.
func TestRegisterDisabledReturns403(t *testing.T) {
	ah := NewAuthHandler(nil, false)
	req := httptest.NewRequest(http.MethodPost, "/auth/register",
		strings.NewReader(`{"username":"ciudadana","password":"Cl4ve.Segura!"}`))
	rec := httptest.NewRecorder()

	ah.Register(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("con el registro deshabilitado esperaba 403, obtuve %d", rec.Code)
	}
}
