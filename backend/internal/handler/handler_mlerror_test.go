package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/vigia/backend/internal/config"
	"github.com/vigia/backend/internal/mlclient"
)

// mlErrorServer simula un servicio ML que falla devolviendo un cuerpo con detalles internos
// (traza, secretos). Verifica que NO se reenvíen al cliente.
func mlErrorServer(t *testing.T, body string) *Handler {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return New(nil, mlclient.New(srv.URL), nil, config.Config{})
}

const _leak = "Traceback (most recent call last) File /app/secret.py line 42: DB password=hunter2"

func TestForecastSanitizaErrorDelML(t *testing.T) {
	h := mlErrorServer(t, _leak)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet,
		"/api/v1/forecast?cod_municipio=11001&categoria=HOMICIDIO", nil)
	h.Forecast(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("esperaba propagar el status 500, obtuve %d", rec.Code)
	}
	if strings.Contains(rec.Body.String(), "Traceback") || strings.Contains(rec.Body.String(), "hunter2") {
		t.Fatalf("el cuerpo crudo del ML se filtró al cliente: %s", rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "servicio de IA") {
		t.Fatalf("esperaba un mensaje saneado, obtuve: %s", rec.Body.String())
	}
}

func TestAssistantSanitizaErrorDelML(t *testing.T) {
	h := mlErrorServer(t, _leak)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/api/v1/assistant",
		strings.NewReader(`{"pregunta":"hola"}`))
	h.Assistant(rec, req)

	if strings.Contains(rec.Body.String(), "Traceback") || strings.Contains(rec.Body.String(), "hunter2") {
		t.Fatalf("el cuerpo crudo del ML se filtró al cliente: %s", rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "servicio de IA") {
		t.Fatalf("esperaba un mensaje saneado, obtuve: %s", rec.Body.String())
	}
}
