// Package realtime consulta señales de seguridad en TIEMPO REAL desde GDELT (prensa mundial),
// como complemento —no sustituto— del dato oficial mensual de la Policía. Lo que devuelve son
// NOTICIAS de prensa (no cifras oficiales de criminalidad); así debe etiquetarse en la UI.
//
// GDELT rate-limita con dureza (≈1 petición / 5 s y penaliza el abuso), por lo que este cliente
// SIEMPRE debe consumirse detrás de una caché (Redis, en el handler): el tráfico público se sirve
// de caché y GDELT se golpea, a lo sumo, una vez por departamento cada pocos minutos.
package realtime

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

const (
	gdeltEndpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
	// Términos de seguridad (ES) para acotar el ruido de prensa a lo relevante del reto.
	securityTerms = `(homicidio OR secuestro OR extorsión OR hurto OR delincuencia OR criminalidad OR "orden público")`
)

// Item es una noticia recuperada (una señal de prensa, NO una cifra oficial).
type Item struct {
	Titulo string `json:"titulo"`
	URL    string `json:"url"`
	Fuente string `json:"fuente"` // dominio de la fuente (p. ej. eltiempo.com)
	Fecha  string `json:"fecha"`  // ISO (AAAA-MM-DD) derivada del seendate de GDELT
}

// Client consulta GDELT. baseURL se parametriza para poder testear con un servidor local.
type Client struct {
	baseURL string
	http    *http.Client
}

// NewClient crea el cliente contra el endpoint real de GDELT (timeout corto: es de cara al usuario).
func NewClient() *Client {
	return &Client{baseURL: gdeltEndpoint, http: &http.Client{Timeout: 10 * time.Second}}
}

// NewClientWithBase inyecta un endpoint alternativo (para tests con httptest).
func NewClientWithBase(base string) *Client {
	return &Client{baseURL: base, http: &http.Client{Timeout: 10 * time.Second}}
}

type gdeltResponse struct {
	Articles []struct {
		URL      string `json:"url"`
		Title    string `json:"title"`
		SeenDate string `json:"seendate"`
		Domain   string `json:"domain"`
	} `json:"articles"`
}

// Recent devuelve hasta `max` noticias de seguridad recientes (última semana). Si `depto` está
// vacío, consulta a nivel NACIONAL (Colombia); si no, acota por el nombre del departamento.
func (c *Client) Recent(ctx context.Context, depto string, max int) ([]Item, error) {
	q := securityTerms + " sourcecountry:CO"
	if depto != "" {
		q = `"` + depto + `" ` + q
	}
	params := url.Values{
		"query":      {q},
		"mode":       {"artlist"},
		"format":     {"json"},
		"timespan":   {"1w"},
		"sort":       {"DateDesc"},
		"maxrecords": {fmt.Sprint(max)},
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"?"+params.Encode(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "VigIA/1.0 (+https://github.com/diegoa-rodriguezc/vigia)")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("gdelt status %d", resp.StatusCode)
	}
	// GDELT devuelve TEXTO PLANO (no JSON) cuando rate-limita → el Decode falla y se reporta como
	// error controlado (el handler degrada a "señal no disponible").
	var gr gdeltResponse
	if err := json.NewDecoder(resp.Body).Decode(&gr); err != nil {
		return nil, fmt.Errorf("respuesta GDELT no-JSON (posible rate-limit): %w", err)
	}

	items := make([]Item, 0, len(gr.Articles))
	for _, a := range gr.Articles {
		if a.URL == "" || a.Title == "" {
			continue
		}
		items = append(items, Item{
			Titulo: a.Title,
			URL:    a.URL,
			Fuente: a.Domain,
			Fecha:  parseSeenDate(a.SeenDate),
		})
	}
	return items, nil
}

// parseSeenDate convierte el "AAAAMMDDTHHMMSSZ" de GDELT a ISO "AAAA-MM-DD"; si falla, lo deja igual.
func parseSeenDate(s string) string {
	t, err := time.Parse("20060102T150405Z", s)
	if err != nil {
		return s
	}
	return t.Format("2006-01-02")
}
