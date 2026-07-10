package auth

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"

	"github.com/vigia/backend/internal/redisstore"
)

type ctxKey int

const claimsKey ctxKey = 0

// Roles conocidos del sistema (los mismos literales que persiste la tabla users).
const (
	RoleAdmin   = "admin"
	RoleCitizen = "citizen"
)

// Middleware agrupa las dependencias para proteger rutas.
type Middleware struct {
	tokens *TokenManager
	store  *redisstore.Store
}

func NewMiddleware(tokens *TokenManager, store *redisstore.Store) *Middleware {
	return &Middleware{tokens: tokens, store: store}
}

// RequireAuth exige un access token válido (Bearer) y no revocado.
func (m *Middleware) RequireAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := bearerToken(r)
		if token == "" {
			writeAuthError(w, http.StatusUnauthorized, "se requiere autenticación")
			return
		}
		claims, err := m.tokens.Parse(token)
		if err != nil {
			writeAuthError(w, http.StatusUnauthorized, "token inválido o expirado")
			return
		}
		// Revocación: si el jti está en la denylist, rechaza. Si Redis no responde
		// (ok=false), se aplica fail-open con alerta: la vida corta del token acota el riesgo.
		if revoked, ok := m.store.IsDenylisted(r.Context(), claims.ID); ok && revoked {
			writeAuthError(w, http.StatusUnauthorized, "sesión revocada")
			return
		} else if !ok {
			slog.Warn("no se pudo verificar la denylist (Redis); se permite el token", "jti", claims.ID)
		}

		ctx := context.WithValue(r.Context(), claimsKey, claims)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// RequireRole exige, además de autenticación, un rol concreto (p. ej. "admin").
// Debe componerse DESPUÉS de RequireAuth.
func (m *Middleware) RequireRole(role string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			claims, ok := ClaimsFromContext(r.Context())
			if !ok || claims.Role != role {
				writeAuthError(w, http.StatusForbidden, "permisos insuficientes")
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// ClaimsFromContext recupera los claims inyectados por RequireAuth.
func ClaimsFromContext(ctx context.Context) (*Claims, bool) {
	c, ok := ctx.Value(claimsKey).(*Claims)
	return c, ok
}

// ContextWithClaims inyecta claims en el contexto igual que RequireAuth; existe para que
// otros paquetes (y sus tests) puedan simular una petición autenticada sin pasar por el
// middleware completo.
func ContextWithClaims(ctx context.Context, c *Claims) context.Context {
	return context.WithValue(ctx, claimsKey, c)
}

func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	if h == "" {
		return ""
	}
	parts := strings.SplitN(h, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
		return ""
	}
	return strings.TrimSpace(parts[1])
}

func writeAuthError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("WWW-Authenticate", "Bearer")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
