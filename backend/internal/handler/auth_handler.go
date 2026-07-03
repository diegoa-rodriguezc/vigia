package handler

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/vigia/backend/internal/auth"
	"github.com/vigia/backend/internal/middleware"
)

// AuthHandler expone los endpoints de autenticación (/auth/*).
type AuthHandler struct {
	svc                 *auth.Service
	registrationEnabled bool
}

func NewAuthHandler(svc *auth.Service, registrationEnabled bool) *AuthHandler {
	return &AuthHandler{svc: svc, registrationEnabled: registrationEnabled}
}

const (
	maxUsernameLen = 64
	maxPasswordLen = 128
)

type loginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type loginResponse struct {
	auth.TokenPair
	User auth.PublicUser `json:"user"`
}

// Login valida credenciales y entrega un par de tokens.
func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var body loginRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "JSON inválido")
		return
	}
	if body.Username == "" || body.Password == "" {
		writeError(w, http.StatusBadRequest, "usuario y contraseña son obligatorios")
		return
	}
	if len(body.Username) > maxUsernameLen || len(body.Password) > maxPasswordLen {
		writeError(w, http.StatusBadRequest, "usuario o contraseña demasiado largos")
		return
	}

	pair, user, err := h.svc.Login(r.Context(), body.Username, body.Password, middleware.ClientIP(r))
	if err != nil {
		switch {
		case errors.Is(err, auth.ErrAccountLocked):
			w.Header().Set("Retry-After", "900")
			writeError(w, http.StatusTooManyRequests, "cuenta bloqueada temporalmente; intenta más tarde")
		case errors.Is(err, auth.ErrInvalidCredentials):
			writeError(w, http.StatusUnauthorized, "credenciales inválidas")
		case errors.Is(err, auth.ErrStoreUnavailable):
			writeError(w, http.StatusServiceUnavailable, "servicio de sesiones no disponible")
		default:
			slog.Error("fallo inesperado en login", "error", err)
			writeError(w, http.StatusInternalServerError, "error interno")
		}
		return
	}
	slog.Info("login exitoso", "usuario", user.Username, "rol", user.Role)
	writeJSON(w, http.StatusOK, loginResponse{TokenPair: pair, User: user})
}

// Register crea una cuenta ciudadana (rol "citizen") y la deja autenticada. Es público (con
// rate-limit estricto, como el login) para que la ciudadanía pueda usar el asistente y el
// pronóstico sin depender de la cuenta administradora.
func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	// Guarda autoritativa: si el despliegue deshabilitó el registro, se rechaza aquí (la UI
	// además oculta el botón, pero el servidor no confía en el cliente).
	if !h.registrationEnabled {
		writeError(w, http.StatusForbidden, "el registro de nuevas cuentas está deshabilitado")
		return
	}
	var body loginRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "JSON inválido")
		return
	}
	if body.Username == "" || body.Password == "" {
		writeError(w, http.StatusBadRequest, "usuario y contraseña son obligatorios")
		return
	}
	// Cota temprana de tamaño (defensa antes del bcrypt); la política fina la aplica el servicio.
	if len(body.Username) > maxUsernameLen || len(body.Password) > maxPasswordLen {
		writeError(w, http.StatusBadRequest, "usuario o contraseña demasiado largos")
		return
	}

	pair, user, err := h.svc.Register(r.Context(), body.Username, body.Password)
	if err != nil {
		var ve auth.ValidationError
		switch {
		case errors.As(err, &ve):
			writeError(w, http.StatusBadRequest, ve.Error())
		case errors.Is(err, auth.ErrUsernameTaken):
			writeError(w, http.StatusConflict, "el nombre de usuario ya está en uso")
		case errors.Is(err, auth.ErrStoreUnavailable):
			writeError(w, http.StatusServiceUnavailable, "servicio de sesiones no disponible")
		default:
			slog.Error("fallo inesperado en registro", "error", err)
			writeError(w, http.StatusInternalServerError, "error interno")
		}
		return
	}
	slog.Info("registro exitoso", "usuario", user.Username, "rol", user.Role)
	writeJSON(w, http.StatusCreated, loginResponse{TokenPair: pair, User: user})
}

type refreshRequest struct {
	RefreshToken string `json:"refresh_token"`
}

// Refresh rota el par de tokens a partir de un refresh token válido.
func (h *AuthHandler) Refresh(w http.ResponseWriter, r *http.Request) {
	var body refreshRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.RefreshToken == "" {
		writeError(w, http.StatusBadRequest, "refresh_token requerido")
		return
	}
	pair, err := h.svc.Refresh(r.Context(), body.RefreshToken)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "refresh token inválido o expirado")
		return
	}
	writeJSON(w, http.StatusOK, pair)
}

// Logout revoca el access token actual y el refresh token enviado. Va tras RequireAuth.
func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	claims, _ := auth.ClaimsFromContext(r.Context())
	var body refreshRequest
	_ = json.NewDecoder(r.Body).Decode(&body) // el refresh es opcional en el cuerpo
	_ = h.svc.Logout(r.Context(), claims, body.RefreshToken)
	w.WriteHeader(http.StatusNoContent)
}

// Me devuelve la identidad del usuario autenticado (para el frontend). Va tras RequireAuth.
func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	claims, ok := auth.ClaimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "no autenticado")
		return
	}
	writeJSON(w, http.StatusOK, auth.PublicUser{
		ID:       claims.Subject,
		Username: claims.Username,
		Role:     claims.Role,
	})
}
