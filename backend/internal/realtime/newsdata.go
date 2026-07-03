package realtime

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// newsDataEndpoint es la API PÚBLICA de newsdata.io (no el `/web/v1/dashboard/...`, que usa la
// sesión del navegador). Requiere `apikey` (gratuita en el panel de newsdata.io).
const newsDataEndpoint = "https://newsdata.io/api/1/latest"

// NewsDataClient consulta newsdata.io. Es la fuente PRIMARIA cuando hay NEWSDATA_API_KEY; si no,
// el backend cae a GDELT (sin token). Implementa la misma interfaz que el cliente GDELT.
type NewsDataClient struct {
	apiKey  string
	baseURL string
	http    *http.Client
}

// NewNewsDataClient crea el cliente contra el endpoint público real de newsdata.io.
func NewNewsDataClient(apiKey string) *NewsDataClient {
	return &NewsDataClient{apiKey: apiKey, baseURL: newsDataEndpoint, http: &http.Client{Timeout: 10 * time.Second}}
}

// newNewsDataClientWithBase inyecta un endpoint alternativo (tests con httptest).
func newNewsDataClientWithBase(apiKey, base string) *NewsDataClient {
	return &NewsDataClient{apiKey: apiKey, baseURL: base, http: &http.Client{Timeout: 10 * time.Second}}
}

type newsDataResponse struct {
	Status  string `json:"status"`
	Results []struct {
		Title      string `json:"title"`
		Link       string `json:"link"`
		SourceID   string `json:"source_id"`
		SourceName string `json:"source_name"`
		PubDate    string `json:"pubDate"`
	} `json:"results"`
}

// Recent devuelve hasta `max` noticias recientes de Colombia. Si `depto` está vacío, consulta a
// nivel nacional; si no, acota por el nombre del departamento (q=<depto> en minúsculas —newsdata no
// lo encuentra en Title-case). Filtra por país (co) e idioma (es) y elimina duplicados.
func (c *NewsDataClient) Recent(ctx context.Context, depto string, max int) ([]Item, error) {
	// Filtros: category=crime enfoca la relevancia a SEGURIDAD (evita deportes/clima); country/
	// language/timezone acotan a Colombia y removeduplicate limpia repetidos. A nivel nacional se
	// usan solo esos; al seleccionar un departamento se añade q=<departamento>.
	params := url.Values{
		"apikey":          {c.apiKey},
		"country":         {"co"},
		"language":        {"es"},
		"category":        {"crime"},
		"removeduplicate": {"1"},
		"timezone":        {"america/bogota"},
	}
	if depto != "" {
		// newsdata.io NO encuentra el nombre en mayúsculas/Title-case ("Antioquia" → 0 resultados);
		// hay que enviarlo en minúsculas ("antioquia"). Se conservan los acentos.
		params.Set("q", strings.ToLower(depto))
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"?"+params.Encode(), nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("newsdata status %d", resp.StatusCode)
	}
	var nr newsDataResponse
	if err := json.NewDecoder(resp.Body).Decode(&nr); err != nil {
		return nil, fmt.Errorf("respuesta newsdata no-JSON: %w", err)
	}
	if nr.Status != "success" {
		return nil, fmt.Errorf("newsdata status=%q", nr.Status)
	}

	items := make([]Item, 0, len(nr.Results))
	for _, a := range nr.Results {
		if a.Link == "" || a.Title == "" {
			continue
		}
		fuente := a.SourceName
		if fuente == "" {
			fuente = a.SourceID
		}
		items = append(items, Item{
			Titulo: a.Title,
			URL:    a.Link,
			Fuente: fuente,
			Fecha:  parseNewsDate(a.PubDate),
		})
		if len(items) >= max {
			break
		}
	}
	return items, nil
}

// parseNewsDate normaliza el "AAAA-MM-DD HH:MM:SS" de newsdata a "AAAA-MM-DD"; degrada con
// elegancia si el formato cambia.
func parseNewsDate(s string) string {
	if t, err := time.Parse("2006-01-02 15:04:05", s); err == nil {
		return t.Format("2006-01-02")
	}
	if len(s) >= 10 {
		return s[:10]
	}
	return s
}
