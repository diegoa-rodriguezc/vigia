// Package mlclient es un cliente HTTP hacia el servicio ML de Python (FastAPI).
package mlclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Client struct {
	baseURL string
	http    *http.Client
}

func New(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		// Amplio: el asistente RAG (LLM local en CPU) puede tardar ~30-90s.
		http: &http.Client{Timeout: 240 * time.Second},
	}
}

// Proxy reenvía una petición al servicio ML y devuelve el cuerpo crudo (JSON).
func (c *Client) Proxy(ctx context.Context, method, path string, payload any) ([]byte, int, error) {
	var body io.Reader
	if payload != nil {
		b, err := json.Marshal(payload)
		if err != nil {
			return nil, 0, err
		}
		body = bytes.NewReader(b)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, http.StatusBadGateway, fmt.Errorf("servicio ML no disponible: %w", err)
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	return data, resp.StatusCode, err
}
