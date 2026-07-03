// Package redisstore centraliza el acceso a Redis para la capa de autenticación:
// almacén de refresh tokens (whitelist con rotación), denylist de access tokens
// (revocación por logout), rate-limiting y bloqueo anti fuerza-bruta de login.
package redisstore

import (
	"context"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
)

// ErrNotFound se devuelve cuando una clave esperada no existe (p. ej. refresh inválido).
var ErrNotFound = errors.New("clave no encontrada en redis")

type Store struct {
	rdb *redis.Client
}

// New construye el cliente desde una URL `redis://host:port/db` y verifica la conexión.
// Devuelve el Store aunque el Ping falle, junto al error, para que el backend pueda
// arrancar en modo degradado (las operaciones fallarán de forma controlada).
func New(ctx context.Context, url string) (*Store, error) {
	opt, err := redis.ParseURL(url)
	if err != nil {
		return nil, err
	}
	rdb := redis.NewClient(opt)
	s := &Store{rdb: rdb}

	pingCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	if err := rdb.Ping(pingCtx).Err(); err != nil {
		return s, err
	}
	return s, nil
}

func (s *Store) Close() error {
	if s == nil || s.rdb == nil {
		return nil
	}
	return s.rdb.Close()
}

// Available indica si Redis responde (para healthchecks y decisiones fail-open/closed).
func (s *Store) Available(ctx context.Context) bool {
	if s.down() {
		return false
	}
	c, cancel := context.WithTimeout(ctx, 1*time.Second)
	defer cancel()
	return s.rdb.Ping(c).Err() == nil
}

// down indica que el Store no es usable (nil o sin cliente), p. ej. por REDIS_URL inválida.
func (s *Store) down() bool { return s == nil || s.rdb == nil }

// ── Refresh tokens (whitelist con TTL) ──

func refreshKey(token string) string { return "refresh:" + token }

// SaveRefresh almacena el refresh token asociado al id de usuario con expiración.
func (s *Store) SaveRefresh(ctx context.Context, token, userID string, ttl time.Duration) error {
	if s.down() {
		return ErrNotFound
	}
	return s.rdb.Set(ctx, refreshKey(token), userID, ttl).Err()
}

// GetRefresh devuelve el id de usuario del refresh token, o ErrNotFound si no existe
// (expirado, rotado o nunca emitido → posible reuso).
func (s *Store) GetRefresh(ctx context.Context, token string) (string, error) {
	if s.down() {
		return "", ErrNotFound
	}
	v, err := s.rdb.Get(ctx, refreshKey(token)).Result()
	if errors.Is(err, redis.Nil) {
		return "", ErrNotFound
	}
	return v, err
}

// DeleteRefresh invalida un refresh token (rotación o logout).
func (s *Store) DeleteRefresh(ctx context.Context, token string) error {
	if s.down() {
		return nil
	}
	return s.rdb.Del(ctx, refreshKey(token)).Err()
}

// ── Denylist de access tokens (revocación por jti) ──

func denyKey(jti string) string { return "denylist:" + jti }

// Denylist marca un access token (por jti) como revocado hasta su expiración natural.
func (s *Store) Denylist(ctx context.Context, jti string, ttl time.Duration) error {
	if s.down() || ttl <= 0 {
		return nil // sin Redis o ya expirado, no hace falta recordarlo
	}
	return s.rdb.Set(ctx, denyKey(jti), "1", ttl).Err()
}

// IsDenylisted indica si un jti fue revocado. El segundo retorno es false si Redis falla
// (el llamador decide la política fail-open/closed).
func (s *Store) IsDenylisted(ctx context.Context, jti string) (revoked bool, ok bool) {
	if s.down() {
		return false, false
	}
	n, err := s.rdb.Exists(ctx, denyKey(jti)).Result()
	if err != nil {
		return false, false
	}
	return n > 0, true
}

// ── Rate limiting (ventana fija por scope+IP) ──

// Allow incrementa el contador `ratelimit:<scope>:<ip>` y lo deja expirar tras `window`.
// Devuelve (permitido, ok). Si Redis falla, ok=false y el llamador aplica fail-open.
func (s *Store) Allow(ctx context.Context, scope, ip string, limit int, window time.Duration) (allowed bool, ok bool) {
	if s.down() {
		return true, false
	}
	key := "ratelimit:" + scope + ":" + ip
	n, err := s.rdb.Incr(ctx, key).Result()
	if err != nil {
		return true, false
	}
	if n == 1 {
		// primera petición de la ventana: fija la expiración
		_ = s.rdb.Expire(ctx, key, window).Err()
	}
	return n <= int64(limit), true
}

// ── Caché de respuestas (p. ej. pronóstico y asistente de IA) ──

// GetCached devuelve el valor cacheado bajo `key`. El segundo retorno es false si no hay
// hit o si Redis no está disponible (el llamador sigue de largo → fail-open).
func (s *Store) GetCached(ctx context.Context, key string) ([]byte, bool) {
	if s.down() {
		return nil, false
	}
	v, err := s.rdb.Get(ctx, key).Bytes()
	if err != nil {
		return nil, false // miss, expirado o Redis caído
	}
	return v, true
}

// SetCached guarda `val` bajo `key` con expiración. Silencioso si Redis no está (fail-open):
// no cachear nunca debe romper la petición.
func (s *Store) SetCached(ctx context.Context, key string, val []byte, ttl time.Duration) {
	if s.down() || ttl <= 0 {
		return
	}
	_ = s.rdb.Set(ctx, key, val, ttl).Err()
}

// ── Bloqueo anti fuerza-bruta de login ──

func loginFailKey(id string) string { return "loginfail:" + id }

// LoginLocked indica si una identidad (usuario o IP) superó el umbral de intentos fallidos.
func (s *Store) LoginLocked(ctx context.Context, id string, threshold int) bool {
	if s.down() {
		return false
	}
	n, err := s.rdb.Get(ctx, loginFailKey(id)).Int()
	if err != nil {
		return false // sin registro o Redis caído → no bloquear (fail-open)
	}
	return n >= threshold
}

// IncrLoginFail suma un intento fallido y (re)fija la ventana de lockout.
func (s *Store) IncrLoginFail(ctx context.Context, id string, window time.Duration) {
	if s.down() {
		return
	}
	key := loginFailKey(id)
	n, err := s.rdb.Incr(ctx, key).Result()
	if err != nil {
		return
	}
	if n == 1 {
		_ = s.rdb.Expire(ctx, key, window).Err()
	}
}

// ResetLoginFail limpia el contador tras un login exitoso.
func (s *Store) ResetLoginFail(ctx context.Context, id string) {
	if s.down() {
		return
	}
	_ = s.rdb.Del(ctx, loginFailKey(id)).Err()
}
