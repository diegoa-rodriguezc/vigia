package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"

	"github.com/vigia/backend/internal/config"
	"github.com/vigia/backend/internal/mlclient"
	"github.com/vigia/backend/internal/redisstore"
)

// newCacheHandler arma un handler con caché habilitada (miniredis) y un servicio ML
// simulado que cuenta cuántas veces se le llama.
func newCacheHandler(t *testing.T, hits *int32) *Handler {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis: %v", err)
	}
	t.Cleanup(mr.Close)
	store, err := redisstore.New(context.Background(), "redis://"+mr.Addr())
	if err != nil {
		t.Fatalf("redisstore: %v", err)
	}

	ml := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		atomic.AddInt32(hits, 1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(ml.Close)

	cfg := config.Config{CacheEnabled: true, CacheForecastTTL: time.Hour, CacheAssistantTTL: time.Hour}
	return New(nil, mlclient.New(ml.URL), store, cfg)
}

func TestForecastCacheHitMiss(t *testing.T) {
	var hits int32
	h := newCacheHandler(t, &hits)
	url := "/api/v1/forecast?cod_municipio=11001&categoria=HOMICIDIO"

	// 1ª llamada → MISS (golpea al ML), guarda en caché.
	rec1 := httptest.NewRecorder()
	h.Forecast(rec1, httptest.NewRequest(http.MethodGet, url, nil))
	if rec1.Code != http.StatusOK || rec1.Header().Get("X-Cache") != "MISS" {
		t.Fatalf("1ª: esperaba 200 MISS, obtuve %d %q", rec1.Code, rec1.Header().Get("X-Cache"))
	}

	// 2ª llamada idéntica → HIT (NO golpea al ML).
	rec2 := httptest.NewRecorder()
	h.Forecast(rec2, httptest.NewRequest(http.MethodGet, url, nil))
	if rec2.Code != http.StatusOK || rec2.Header().Get("X-Cache") != "HIT" {
		t.Fatalf("2ª: esperaba 200 HIT, obtuve %d %q", rec2.Code, rec2.Header().Get("X-Cache"))
	}
	if rec2.Body.String() != rec1.Body.String() {
		t.Fatal("la respuesta cacheada debería ser idéntica")
	}
	if got := atomic.LoadInt32(&hits); got != 1 {
		t.Fatalf("el ML debió llamarse 1 vez, se llamó %d", got)
	}

	// 3ª llamada con ?nocache=1 → vuelve a golpear al ML (bypass).
	rec3 := httptest.NewRecorder()
	h.Forecast(rec3, httptest.NewRequest(http.MethodGet, url+"&nocache=1", nil))
	if rec3.Header().Get("X-Cache") != "MISS" {
		t.Fatalf("nocache: esperaba MISS, obtuve %q", rec3.Header().Get("X-Cache"))
	}
	if got := atomic.LoadInt32(&hits); got != 2 {
		t.Fatalf("con nocache el ML debió llamarse 2 veces en total, fueron %d", got)
	}
}

func TestAssistantCacheHitMiss(t *testing.T) {
	var hits int32
	h := newCacheHandler(t, &hits)
	body := `{"pregunta":"¿Cuántos homicidios hubo en Bogotá?"}`

	rec1 := httptest.NewRecorder()
	h.Assistant(rec1, httptest.NewRequest(http.MethodPost, "/api/v1/assistant", strings.NewReader(body)))
	if rec1.Header().Get("X-Cache") != "MISS" {
		t.Fatalf("1ª: esperaba MISS, obtuve %q", rec1.Header().Get("X-Cache"))
	}

	rec2 := httptest.NewRecorder()
	h.Assistant(rec2, httptest.NewRequest(http.MethodPost, "/api/v1/assistant", strings.NewReader(body)))
	if rec2.Header().Get("X-Cache") != "HIT" {
		t.Fatalf("2ª: esperaba HIT, obtuve %q", rec2.Header().Get("X-Cache"))
	}
	if got := atomic.LoadInt32(&hits); got != 1 {
		t.Fatalf("el ML debió llamarse 1 vez, se llamó %d", got)
	}
}
