package auth

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"

	"github.com/vigia/backend/internal/redisstore"
)

// ── helpers ──

func newTestStore(t *testing.T) *redisstore.Store {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis: %v", err)
	}
	t.Cleanup(mr.Close)
	store, err := redisstore.New(context.Background(), "redis://"+mr.Addr())
	if err != nil {
		t.Fatalf("redisstore: %v", err)
	}
	return store
}

// fakeUsers implementa UserStore en memoria.
type fakeUsers struct {
	byName map[string]User
	byID   map[string]User
}

func newFakeUsers(users ...User) *fakeUsers {
	f := &fakeUsers{byName: map[string]User{}, byID: map[string]User{}}
	for _, u := range users {
		f.byName[u.Username] = u
		f.byID[u.ID] = u
	}
	return f
}

func (f *fakeUsers) GetUserByUsername(_ context.Context, username string) (User, error) {
	if u, ok := f.byName[username]; ok {
		return u, nil
	}
	return User{}, ErrUserNotFound
}

func (f *fakeUsers) GetUserByID(_ context.Context, id string) (User, error) {
	if u, ok := f.byID[id]; ok {
		return u, nil
	}
	return User{}, ErrUserNotFound
}

func adminUser(t *testing.T, password string) User {
	t.Helper()
	hash, err := HashPassword(password)
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	return User{ID: "1", Username: "admin", Role: "admin", PasswordHash: hash}
}

// ── password ──

func TestPasswordHashAndVerify(t *testing.T) {
	hash, err := HashPassword("s3cr3t!")
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	if !VerifyPassword(hash, "s3cr3t!") {
		t.Fatal("la contraseña correcta debería verificar")
	}
	if VerifyPassword(hash, "otra") {
		t.Fatal("una contraseña errónea no debería verificar")
	}
}

// ── jwt ──

func TestJWTSignAndParse(t *testing.T) {
	tm := NewTokenManager("secreto-de-pruebas", 15*time.Minute)
	token, jti, exp, err := tm.Sign("1", "admin", "admin", time.Now())
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	if jti == "" || exp.Before(time.Now()) {
		t.Fatal("jti/exp inválidos")
	}
	claims, err := tm.Parse(token)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if claims.Subject != "1" || claims.Username != "admin" || claims.Role != "admin" {
		t.Fatalf("claims inesperados: %+v", claims)
	}
}

func TestJWTRejectsExpired(t *testing.T) {
	tm := NewTokenManager("secreto", time.Minute)
	// Firma con marca de tiempo en el pasado (ya expirado).
	token, _, _, err := tm.Sign("1", "admin", "admin", time.Now().Add(-2*time.Hour))
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	if _, err := tm.Parse(token); err != ErrExpired {
		t.Fatalf("esperaba ErrExpired, obtuve %v", err)
	}
}

func TestJWTRejectsWrongSecret(t *testing.T) {
	signer := NewTokenManager("secreto-A", 15*time.Minute)
	verifier := NewTokenManager("secreto-B", 15*time.Minute)
	token, _, _, _ := signer.Sign("1", "admin", "admin", time.Now())
	if _, err := verifier.Parse(token); err != ErrInvalidToken {
		t.Fatalf("esperaba ErrInvalidToken con secreto distinto, obtuve %v", err)
	}
}

// ── service: login / refresh / logout ──

func TestLoginRefreshRotation(t *testing.T) {
	store := newTestStore(t)
	tm := NewTokenManager("secreto", 15*time.Minute)
	svc := NewService(tm, store, newFakeUsers(adminUser(t, "clave")), time.Hour)
	ctx := context.Background()

	pair, user, err := svc.Login(ctx, "admin", "clave", "10.0.0.1")
	if err != nil {
		t.Fatalf("login: %v", err)
	}
	if pair.AccessToken == "" || pair.RefreshToken == "" || user.Username != "admin" {
		t.Fatalf("par/usuario inesperados: %+v %+v", pair, user)
	}

	// Refresh rota: emite par nuevo e invalida el refresh usado (un solo uso).
	pair2, err := svc.Refresh(ctx, pair.RefreshToken)
	if err != nil {
		t.Fatalf("refresh: %v", err)
	}
	if pair2.RefreshToken == pair.RefreshToken {
		t.Fatal("el refresh token debería rotar")
	}
	if _, err := svc.Refresh(ctx, pair.RefreshToken); err == nil {
		t.Fatal("reusar el refresh anterior debería fallar (rotación)")
	}
}

func TestLoginInvalidCredentialsAndLockout(t *testing.T) {
	store := newTestStore(t)
	tm := NewTokenManager("secreto", 15*time.Minute)
	svc := NewService(tm, store, newFakeUsers(adminUser(t, "clave")), time.Hour)
	ctx := context.Background()

	// Usuario inexistente y contraseña errónea devuelven el MISMO error (anti-enumeración).
	if _, _, err := svc.Login(ctx, "fantasma", "x", "10.0.0.1"); err != ErrInvalidCredentials {
		t.Fatalf("esperaba ErrInvalidCredentials, obtuve %v", err)
	}

	// Tras superar el umbral de fallos desde una IP, esa (usuario, IP) queda bloqueada.
	for i := 0; i < loginFailThreshold; i++ {
		_, _, _ = svc.Login(ctx, "admin", "mala", "10.0.0.1")
	}
	if _, _, err := svc.Login(ctx, "admin", "clave", "10.0.0.1"); err != ErrAccountLocked {
		t.Fatalf("esperaba ErrAccountLocked tras %d fallos, obtuve %v", loginFailThreshold, err)
	}

	// El lockout es por (usuario, IP): el MISMO usuario desde OTRA IP NO está bloqueado
	// (evita un DoS dirigido a la cuenta admin). Debe poder autenticarse con éxito.
	if _, _, err := svc.Login(ctx, "admin", "clave", "10.0.0.2"); err != nil {
		t.Fatalf("el admin desde otra IP no debería estar bloqueado, obtuve %v", err)
	}
}

// ── middleware ──

func TestRequireAuthMiddleware(t *testing.T) {
	store := newTestStore(t)
	tm := NewTokenManager("secreto", 15*time.Minute)
	svc := NewService(tm, store, newFakeUsers(adminUser(t, "clave")), time.Hour)
	mw := NewMiddleware(tm, store)
	ctx := context.Background()

	ok := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	protected := mw.RequireAuth(ok)

	// Sin token → 401.
	rec := httptest.NewRecorder()
	protected.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/x", nil))
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("sin token esperaba 401, obtuve %d", rec.Code)
	}

	// Con token válido → 200.
	pair, _, err := svc.Login(ctx, "admin", "clave", "10.0.0.1")
	if err != nil {
		t.Fatalf("login: %v", err)
	}
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Authorization", "Bearer "+pair.AccessToken)
	rec = httptest.NewRecorder()
	protected.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("con token válido esperaba 200, obtuve %d", rec.Code)
	}

	// Tras logout (denylist) el mismo token → 401.
	claims, _ := tm.Parse(pair.AccessToken)
	if err := svc.Logout(ctx, claims, pair.RefreshToken); err != nil {
		t.Fatalf("logout: %v", err)
	}
	req2 := httptest.NewRequest(http.MethodGet, "/x", nil)
	req2.Header.Set("Authorization", "Bearer "+pair.AccessToken)
	rec = httptest.NewRecorder()
	protected.ServeHTTP(rec, req2)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("token revocado esperaba 401, obtuve %d", rec.Code)
	}
}
