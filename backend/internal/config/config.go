// Package config carga la configuración desde variables de entorno (12-factor).
package config

import (
	"log/slog"
	"os"
	"strconv"
	"time"
)

// defaultDevSecret es el secreto JWT de ejemplo. En producción está PROHIBIDO usarlo:
// si APP_ENV=production y JWT_SECRET está vacío o es igual a este valor, el proceso aborta.
const defaultDevSecret = "cambia-esto-por-un-secreto-largo-y-aleatorio"

// defaultAdminPassword es la contraseña de admin de DEMO que viaja en el repositorio
// (.env.example, docker-compose). Es "fuerte" según la política, así que ValidatePassword NO la
// rechaza; se detecta aquí como valor público por defecto (ver InsecureDefaults). En producción,
// su uso aborta el arranque (fail-closed), igual que el JWT_SECRET de ejemplo.
const defaultAdminPassword = "Demo.VigIA.2026"

type Config struct {
	Port           string
	DatabaseURL    string
	MLApiURL       string
	AllowedOrigins string
	AppEnv         string

	// Autenticación
	JWTSecret            string
	JWTExpiration        time.Duration
	JWTRefreshExpiration time.Duration
	RedisURL             string
	AdminUsername        string
	AdminPassword        string

	// RegistrationEnabled: si false, el alta pública de cuentas ciudadanas (POST /auth/register)
	// se rechaza con 403 y la UI oculta el botón "Crear cuenta". Default true (el asistente
	// ciudadano es abierto); ponerlo en false para un despliegue institucional cerrado.
	RegistrationEnabled bool

	// TrustProxyHeaders: si true, se confía en X-Forwarded-For / X-Real-IP para
	// determinar la IP del cliente (rate-limit y lockout). Debe activarse SOLO cuando el
	// backend está tras un proxy inverso de confianza que reescribe esas cabeceras; en
	// caso contrario un atacante podría falsificarlas para evadir el rate-limit. Default false.
	TrustProxyHeaders bool

	// Rate limiting (peticiones por minuto, por IP)
	RateLimitPublic int
	RateLimitLogin  int

	// Caché de respuestas de IA en Redis
	CacheEnabled      bool
	CacheForecastTTL  time.Duration
	CacheAssistantTTL time.Duration
}

func Load() Config {
	appEnv := env("APP_ENV", "development")
	// Se resuelve un secreto utilizable (sustituyendo el de desarrollo si viene vacío) para que el
	// app arranque; la decisión de AVISAR (dev) o ABORTAR (prod) por usar valores públicos por
	// defecto se centraliza en InsecureDefaults, que aplica el backend en main (fail-closed).
	secret := env("JWT_SECRET", "")
	if secret == "" {
		secret = defaultDevSecret
	}

	return Config{
		Port:           env("BACKEND_PORT", "8080"),
		DatabaseURL:    env("DATABASE_URL", "postgres://vigia:vigia_dev_password@localhost:5432/vigia?sslmode=disable"),
		MLApiURL:       env("ML_API_URL", "http://localhost:8000"),
		AllowedOrigins: env("CORS_ALLOWED_ORIGINS", "http://localhost:5173"),
		AppEnv:         appEnv,

		JWTSecret:            secret,
		JWTExpiration:        envDuration("JWT_EXPIRATION", 15*time.Minute),
		JWTRefreshExpiration: envDuration("JWT_REFRESH_EXPIRATION", 168*time.Hour),
		RedisURL:             env("REDIS_URL", "redis://localhost:6379/0"),
		AdminUsername:        env("ADMIN_USERNAME", "admin"),
		// Default de DEMO (cumple la política) solo para arranque local; en producción DEBE
		// sobreescribirse vía ADMIN_PASSWORD (si es débil o el default público, main.go aborta).
		AdminPassword: env("ADMIN_PASSWORD", defaultAdminPassword),

		RegistrationEnabled: envBool("REGISTRATION_ENABLED", true),

		TrustProxyHeaders: envBool("TRUST_PROXY_HEADERS", false),

		RateLimitPublic: envInt("RATE_LIMIT_PUBLIC", 120),
		RateLimitLogin:  envInt("RATE_LIMIT_LOGIN", 10),

		CacheEnabled:      envBool("CACHE_ENABLED", true),
		CacheForecastTTL:  envDuration("CACHE_FORECAST_TTL", 6*time.Hour),
		CacheAssistantTTL: envDuration("CACHE_ASSISTANT_TTL", time.Hour),
	}
}

// InsecureDefaults devuelve la lista de secretos que siguen en su valor PÚBLICO por defecto (el
// que viaja en el repositorio / .env.example). Es una función PURA: no loguea ni aborta. El
// backend la consume al arrancar para AVISAR en desarrollo y ABORTAR en producción (fail-closed),
// igual que se hace con contraseñas débiles. Detecta el default conocido —que la política de
// fuerza NO atrapa, porque `Demo.VigIA.2026` es "fuerte"— además del JWT vacío o de ejemplo.
func InsecureDefaults(c Config) []string {
	var out []string
	if c.JWTSecret == "" || c.JWTSecret == defaultDevSecret {
		out = append(out, "JWT_SECRET (vacío o el valor de ejemplo del repositorio)")
	}
	if c.AdminPassword == defaultAdminPassword {
		out = append(out, "ADMIN_PASSWORD (la contraseña de demo pública del repositorio)")
	}
	return out
}

func envBool(key string, def bool) bool {
	if v := os.Getenv(key); v != "" {
		if b, err := strconv.ParseBool(v); err == nil {
			return b
		}
		slog.Warn("booleano inválido en variable de entorno; usando valor por defecto", "key", key, "valor", v)
	}
	return def
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envDuration(key string, def time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
		slog.Warn("duración inválida en variable de entorno; usando valor por defecto", "key", key, "valor", v)
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
		slog.Warn("entero inválido en variable de entorno; usando valor por defecto", "key", key, "valor", v)
	}
	return def
}
