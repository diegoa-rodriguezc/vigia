// Comando principal de la API REST de VigIA (BFF).
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/vigia/backend/internal/auth"
	"github.com/vigia/backend/internal/config"
	"github.com/vigia/backend/internal/mlclient"
	"github.com/vigia/backend/internal/redisstore"
	"github.com/vigia/backend/internal/repository"
	"github.com/vigia/backend/internal/server"
)

// runHealthcheck consulta el endpoint de salud local y termina con código 0 (sano) o 1.
// Pensado para el HEALTHCHECK del contenedor distroless, que no tiene shell ni curl.
func runHealthcheck() {
	port := os.Getenv("BACKEND_PORT")
	if port == "" {
		port = "8080"
	}
	client := http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get("http://127.0.0.1:" + port + "/api/v1/health")
	if err != nil {
		os.Exit(1)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		os.Exit(1)
	}
}

func main() {
	// Subcomando de healthcheck para el contenedor distroless (sin shell ni curl): el
	// propio binario consulta su endpoint de salud. Lo usa el HEALTHCHECK de docker-compose
	// (`/api healthcheck`).
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		runHealthcheck()
		return
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg := config.Load()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Repositorio de datos (PostgreSQL). No aborta el arranque si la BD aún no está:
	// los endpoints de datos responderán 503 hasta que el pipeline cargue las tablas.
	repo, err := repository.New(ctx, cfg.DatabaseURL)
	if err != nil {
		logger.Warn("no se pudo conectar a la base de datos al inicio", "error", err)
	}

	// Almacén Redis (refresh tokens, denylist, rate-limit). Tampoco aborta: si Redis no
	// está, login/refresh fallarán de forma controlada y el rate-limit hará fail-open.
	store, err := redisstore.New(ctx, cfg.RedisURL)
	if err != nil {
		logger.Warn("no se pudo conectar a Redis al inicio", "error", err)
	}

	// Política de contraseñas para el admin. En producción es un requisito (fail-closed,
	// coherente con el JWT_SECRET); en desarrollo solo se advierte para no frenar la demo.
	if err := auth.ValidatePassword(cfg.AdminPassword); err != nil {
		if cfg.AppEnv == "production" {
			logger.Error("ADMIN_PASSWORD no cumple la política de seguridad en producción", "error", err)
			os.Exit(1)
		}
		logger.Warn("ADMIN_PASSWORD débil (aceptable solo en desarrollo)", "motivo", err)
	}

	// Esquema de auth + administrador. Requiere BD disponible.
	if repo.Available() {
		if err := repo.EnsureAuthSchema(ctx); err != nil {
			logger.Error("no se pudo crear el esquema de auth", "error", err)
		} else if hash, herr := auth.HashPassword(cfg.AdminPassword); herr == nil {
			if err := repo.UpsertAdmin(ctx, cfg.AdminUsername, hash); err != nil {
				logger.Error("no se pudo insertar el usuario admin", "error", err)
			} else {
				logger.Info("usuario admin asegurado", "usuario", cfg.AdminUsername)
			}
		}
	} else {
		logger.Warn("BD no disponible al inicio; el admin se insertará en el próximo arranque con BD")
	}

	tokens := auth.NewTokenManager(cfg.JWTSecret, cfg.JWTExpiration)
	authSvc := auth.NewService(tokens, store, repo, cfg.JWTRefreshExpiration)

	ml := mlclient.New(cfg.MLApiURL)
	router := server.New(cfg, repo, ml, authSvc, tokens, store)

	srv := &http.Server{
		Addr:        ":" + cfg.Port,
		Handler:     router,
		ReadTimeout: 15 * time.Second,
		// WriteTimeout amplio: el endpoint del asistente RAG reenvía a un LLM local
		// (Ollama en CPU) que puede tardar ~30-90s en generar la respuesta.
		WriteTimeout: 250 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		logger.Info("API VigIA escuchando", "puerto", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("fallo del servidor", "error", err)
			os.Exit(1)
		}
	}()

	// Apagado ordenado
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	logger.Info("apagando…")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error("apagado forzado", "error", err)
	}
	if repo != nil {
		repo.Close()
	}
	if store != nil {
		_ = store.Close()
	}
}
