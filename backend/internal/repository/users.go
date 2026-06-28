package repository

import (
	"context"
	"errors"
	"strconv"

	"github.com/jackc/pgx/v5"

	"github.com/vigia/backend/internal/auth"
)

// EnsureAuthSchema crea la tabla `users` si no existe. Siguiendo el principio del
// proyecto (el esquema vive en el código que lo inserta), se ejecuta al arrancar el
// backend en vez de depender de db/init, que solo corre con un volumen de BD nuevo.
func (r *Repository) EnsureAuthSchema(ctx context.Context) error {
	if !r.Available() {
		return ErrNoDB
	}
	_, err := r.pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS users (
			id            BIGSERIAL PRIMARY KEY,
			username      TEXT UNIQUE NOT NULL,
			password_hash TEXT NOT NULL,
			role          TEXT NOT NULL DEFAULT 'citizen',
			created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
		)`)
	return err
}

// UpsertAdmin crea o actualiza el usuario administrador con el hash dado (rol admin).
// Re-ejecutable: en cada arranque alinea el admin con las credenciales del entorno.
func (r *Repository) UpsertAdmin(ctx context.Context, username, passwordHash string) error {
	if !r.Available() {
		return ErrNoDB
	}
	_, err := r.pool.Exec(ctx, `
		INSERT INTO users (username, password_hash, role)
		VALUES ($1, $2, 'admin')
		ON CONFLICT (username)
		DO UPDATE SET password_hash = EXCLUDED.password_hash, role = 'admin'`,
		username, passwordHash)
	return err
}

// GetUserByUsername implementa auth.UserStore.
func (r *Repository) GetUserByUsername(ctx context.Context, username string) (auth.User, error) {
	return r.queryUser(ctx,
		`SELECT id, username, password_hash, role FROM users WHERE username = $1`, username)
}

// GetUserByID implementa auth.UserStore.
func (r *Repository) GetUserByID(ctx context.Context, id string) (auth.User, error) {
	uid, err := strconv.ParseInt(id, 10, 64)
	if err != nil {
		return auth.User{}, auth.ErrUserNotFound
	}
	return r.queryUser(ctx,
		`SELECT id, username, password_hash, role FROM users WHERE id = $1`, uid)
}

func (r *Repository) queryUser(ctx context.Context, query string, arg any) (auth.User, error) {
	if !r.Available() {
		return auth.User{}, ErrNoDB
	}
	var (
		id                           int64
		username, passwordHash, role string
	)
	err := r.pool.QueryRow(ctx, query, arg).Scan(&id, &username, &passwordHash, &role)
	if errors.Is(err, pgx.ErrNoRows) {
		return auth.User{}, auth.ErrUserNotFound
	}
	if err != nil {
		return auth.User{}, mapErr(err)
	}
	return auth.User{
		ID:           strconv.FormatInt(id, 10),
		Username:     username,
		Role:         role,
		PasswordHash: passwordHash,
	}, nil
}
