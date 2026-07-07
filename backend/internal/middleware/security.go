package middleware

import "net/http"

// SecurityHeaders añade cabeceras de endurecimiento a todas las respuestas.
//   - X-Content-Type-Options: evita el "MIME sniffing".
//   - X-Frame-Options: impide el embebido en iframes (clickjacking).
//   - Referrer-Policy: no filtra la URL a terceros.
//   - Strict-Transport-Security: fuerza HTTPS (solo surte efecto cuando la respuesta viaja por TLS).
func SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-Frame-Options", "DENY")
		h.Set("Referrer-Policy", "no-referrer")
		h.Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		next.ServeHTTP(w, r)
	})
}
