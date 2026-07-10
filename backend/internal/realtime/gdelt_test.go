package realtime

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRecentParseArticles(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"articles":[
			{"url":"https://eltiempo.com/n1","title":"Titular 1","seendate":"20260115T120000Z","domain":"eltiempo.com"},
			{"url":"https://semana.com/n2","title":"Titular 2","seendate":"20260114T090000Z","domain":"semana.com"},
			{"url":"","title":"sin url — se descarta","seendate":"20260113T090000Z","domain":"x.com"}
		]}`))
	}))
	defer srv.Close()

	c := NewClientWithBase(srv.URL)
	items, err := c.Recent(context.Background(), "Antioquia", 12)
	if err != nil {
		t.Fatalf("Recent: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("esperaba 2 items (el tercero sin URL se descarta), obtuve %d", len(items))
	}
	if items[0].Fuente != "eltiempo.com" || items[0].Fecha != "2026-01-15" {
		t.Fatalf("resultado inesperado: %+v", items[0])
	}
}

func TestRecentRateLimitedIsError(t *testing.T) {
	// GDELT devuelve texto plano al rate-limitar → debe reportarse como error (no JSON).
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("Please limit requests to one every 5 seconds"))
	}))
	defer srv.Close()

	if _, err := NewClientWithBase(srv.URL).Recent(context.Background(), "", 12); err == nil {
		t.Fatal("una respuesta no-JSON (rate-limit) debería devolver error")
	}
}

func TestDepartamentoNombre(t *testing.T) {
	if n, ok := DepartamentoNombre("05"); !ok || n != "Antioquia" {
		t.Fatalf("05 debería ser Antioquia, obtuve %q ok=%v", n, ok)
	}
	if _, ok := DepartamentoNombre("00"); ok {
		t.Fatal("00 no es un departamento válido")
	}
}
