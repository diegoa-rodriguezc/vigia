package realtime

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNewsDataParseResults(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"success","totalResults":2,"results":[
			{"title":"Titular 1","link":"https://eltiempo.com/n1","source_id":"eltiempo","source_name":"El Tiempo","pubDate":"2026-01-15 12:30:00"},
			{"title":"Titular 2","link":"https://semana.com/n2","source_id":"semana","source_name":"Semana","pubDate":"2026-01-14 09:00:00"},
			{"title":"sin link — se descarta","link":"","source_id":"x","source_name":"X","pubDate":"2026-01-13 09:00:00"}
		]}`))
	}))
	defer srv.Close()

	c := newNewsDataClientWithBase("KEY", srv.URL)
	items, err := c.Recent(context.Background(), "Antioquia", 12)
	if err != nil {
		t.Fatalf("Recent: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("esperaba 2 items (el tercero sin link se descarta), obtuve %d", len(items))
	}
	if items[0].Fuente != "El Tiempo" || items[0].Fecha != "2026-01-15" {
		t.Fatalf("parseo inesperado: %+v", items[0])
	}
}

func TestNewsDataLowercasesQuery(t *testing.T) {
	// newsdata.io no encuentra el departamento en Title-case → el cliente debe enviar q en minúsculas.
	var gotQ string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQ = r.URL.Query().Get("q")
		_, _ = w.Write([]byte(`{"status":"success","results":[]}`))
	}))
	defer srv.Close()

	if _, err := newNewsDataClientWithBase("KEY", srv.URL).Recent(context.Background(), "Antioquia", 12); err != nil {
		t.Fatalf("Recent: %v", err)
	}
	if gotQ != "antioquia" {
		t.Fatalf("q debería ir en minúsculas (antioquia), obtuve %q", gotQ)
	}
}

func TestNewsDataErrorStatusIsError(t *testing.T) {
	// newsdata devuelve status != "success" ante error (p. ej. key inválida) → error controlado.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"error","results":{"message":"Invalid API key"}}`))
	}))
	defer srv.Close()

	if _, err := newNewsDataClientWithBase("BAD", srv.URL).Recent(context.Background(), "", 12); err == nil {
		t.Fatal("un status != success debería devolver error")
	}
}

func TestNewsDataRespectsMax(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"success","results":[
			{"title":"a","link":"http://a","source_name":"A","pubDate":"2026-01-15 00:00:00"},
			{"title":"b","link":"http://b","source_name":"B","pubDate":"2026-01-15 00:00:00"},
			{"title":"c","link":"http://c","source_name":"C","pubDate":"2026-01-15 00:00:00"}
		]}`))
	}))
	defer srv.Close()

	items, err := newNewsDataClientWithBase("KEY", srv.URL).Recent(context.Background(), "", 2)
	if err != nil {
		t.Fatalf("Recent: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("max=2 debería truncar a 2, obtuve %d", len(items))
	}
}
