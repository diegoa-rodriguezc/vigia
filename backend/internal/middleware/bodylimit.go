package middleware

import "net/http"

// MaxBody limita el tamaño del cuerpo de la petición a maxBytes. Envuelve r.Body con
// http.MaxBytesReader, de modo que leerlo (io.ReadAll o json.Decode) devuelve error en cuanto
// se supera el tope, en vez de agotar memoria con un cuerpo gigante (vector de DoS). Se aplica
// globalmente; en peticiones sin cuerpo (GET) es inocuo.
func MaxBody(maxBytes int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Body != nil {
				r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
			}
			next.ServeHTTP(w, r)
		})
	}
}
