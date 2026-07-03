package middleware

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMaxBodyRejectsOversized(t *testing.T) {
	var readErr error
	h := MaxBody(8)(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		_, readErr = io.ReadAll(r.Body)
	}))
	req := httptest.NewRequest(http.MethodPost, "/x", strings.NewReader("0123456789ABCDEF")) // 16 > 8
	h.ServeHTTP(httptest.NewRecorder(), req)
	if readErr == nil {
		t.Fatal("leer un cuerpo mayor al tope debería devolver error")
	}
}

func TestMaxBodyAllowsSmall(t *testing.T) {
	var body []byte
	var readErr error
	h := MaxBody(1024)(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		body, readErr = io.ReadAll(r.Body)
	}))
	req := httptest.NewRequest(http.MethodPost, "/x", strings.NewReader("hola"))
	h.ServeHTTP(httptest.NewRecorder(), req)
	if readErr != nil || string(body) != "hola" {
		t.Fatalf("un cuerpo pequeño debería leerse OK: body=%q err=%v", body, readErr)
	}
}
