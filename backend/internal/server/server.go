// Package server configura el router HTTP (chi) y monta las rutas de la API.
package server

import (
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/vigia/backend/internal/auth"
	"github.com/vigia/backend/internal/config"
	"github.com/vigia/backend/internal/handler"
	"github.com/vigia/backend/internal/middleware"
	"github.com/vigia/backend/internal/mlclient"
	"github.com/vigia/backend/internal/redisstore"
	"github.com/vigia/backend/internal/repository"
)

// New construye el router con middlewares y rutas montadas en /api/v1.
//
// Modelo de seguridad híbrido:
//   - Lectura de datos abiertos: pública, con rate-limit por IP.
//   - Endpoints de IA (/forecast, /assistant) y operaciones: requieren JWT (RequireAuth).
//   - /auth/*: login (rate-limit estricto), refresh y logout.
func New(
	cfg config.Config,
	repo *repository.Repository,
	ml *mlclient.Client,
	authSvc *auth.Service,
	tokens *auth.TokenManager,
	store *redisstore.Store,
) http.Handler {
	r := chi.NewRouter()

	r.Use(chimw.RequestID)
	// RealIP reescribe RemoteAddr desde X-Forwarded-For / X-Real-IP. Solo se activa si el
	// despliegue declara estar tras un proxy de confianza (TRUST_PROXY_HEADERS=true); de lo
	// contrario esas cabeceras son falsificables y permitirían evadir el rate-limit/lockout.
	if cfg.TrustProxyHeaders {
		r.Use(chimw.RealIP)
	}
	r.Use(chimw.Recoverer)
	r.Use(chimw.Timeout(240 * time.Second))
	r.Use(middleware.SecurityHeaders)
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   strings.Split(cfg.AllowedOrigins, ","),
		AllowedMethods:   []string{"GET", "POST", "OPTIONS"},
		AllowedHeaders:   []string{"Content-Type", "Authorization"},
		ExposedHeaders:   []string{"X-Total-Count"}, // total de paginación legible por el navegador
		AllowCredentials: false,
		MaxAge:           300,
	}))

	h := handler.New(repo, ml, store, cfg)
	ah := handler.NewAuthHandler(authSvc)
	mw := auth.NewMiddleware(tokens, store)

	publicLimit := middleware.RateLimit(store, "public", cfg.RateLimitPublic)
	loginLimit := middleware.RateLimit(store, "login", cfg.RateLimitLogin)

	r.Route("/api/v1", func(r chi.Router) {
		// Salud: pública y sin límite (la usan el frontend y los healthchecks).
		r.Get("/health", h.Health)

		// Autenticación.
		r.Group(func(r chi.Router) {
			r.With(loginLimit).Post("/auth/login", ah.Login)
			r.With(loginLimit).Post("/auth/refresh", ah.Refresh)
			r.With(mw.RequireAuth).Post("/auth/logout", ah.Logout)
			r.With(mw.RequireAuth).Get("/auth/me", ah.Me)
		})

		// Lectura pública de datos abiertos (con rate-limit por IP).
		r.Group(func(r chi.Router) {
			r.Use(publicLimit)
			r.Get("/crimes/summary", h.Summary)
			r.Get("/crimes/stats", h.Stats)
			r.Get("/crimes/municipios", h.Municipios)
			r.Get("/crimes/departamentos", h.Departamentos)
			r.Get("/crimes/categories", h.Categories)
			r.Get("/crimes/municipio", h.MunicipioDetalle)
			r.Get("/crimes/timeseries", h.TimeSeries)
			r.Get("/anomalies", h.Anomalies)
			r.Get("/monitoring", h.Monitoring)
			// Capa "Justicia" (Fiscalía): embudo de judicialización.
			r.Get("/justicia/resumen", h.JusticiaResumen)
			r.Get("/justicia/municipios", h.JusticiaMunicipios)
			r.Get("/justicia/departamentos", h.JusticiaDepartamentos)
			r.Get("/justicia/municipio", h.JusticiaMunicipioDetalle)
		})

		// Endpoints de IA: caros, protegidos con JWT (y rate-limit).
		r.Group(func(r chi.Router) {
			r.Use(publicLimit)
			r.Use(mw.RequireAuth)
			r.Get("/forecast", h.Forecast)
			r.Get("/simulate", h.Simulate)
			r.Post("/assistant", h.Assistant)
		})
	})

	return r
}
