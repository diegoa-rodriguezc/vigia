// Package middleware contiene middlewares HTTP transversales (rate-limiting y
// cabeceras de seguridad) que complementan a los de chi.
package middleware

import (
	"encoding/json"
	"net"
	"net/http"
	"time"

	"github.com/vigia/backend/internal/redisstore"
)

// RateLimit construye un middleware que limita a `limit` peticiones por minuto y por IP,
// usando un contador en Redis (ventana fija). `scope` separa contadores por grupo de
// rutas (p. ej. "public" vs "login"). Si Redis no responde, aplica fail-open (no bloquea
// el tráfico legítimo) para no convertir una caída de Redis en una caída del servicio.
func RateLimit(store *redisstore.Store, scope string, limit int) func(http.Handler) http.Handler {
	const window = time.Minute
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ip := ClientIP(r)
			allowed, ok := store.Allow(r.Context(), scope, ip, limit, window)
			if ok && !allowed {
				w.Header().Set("Retry-After", "60")
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				w.WriteHeader(http.StatusTooManyRequests)
				_ = json.NewEncoder(w).Encode(map[string]string{
					"error": "demasiadas peticiones; intenta de nuevo en un minuto",
				})
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// ClientIP devuelve la IP del cliente para rate-limit y lockout. Extrae el host de
// RemoteAddr (que suele venir como "ip:puerto") para que el contador sea por IP y no por
// conexión. Si el backend corre tras un proxy de confianza (TRUST_PROXY_HEADERS=true), el
// middleware RealIP de chi ya habrá fijado RemoteAddr a la IP real (sin puerto).
func ClientIP(r *http.Request) string {
	addr := r.RemoteAddr
	if addr == "" {
		return "unknown"
	}
	if host, _, err := net.SplitHostPort(addr); err == nil {
		return host
	}
	return addr // ya es solo IP (p. ej. tras RealIP)
}
