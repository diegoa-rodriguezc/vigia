package auth

import (
	"context"
	"crypto/rand"
	"errors"
	"time"

	"golang.org/x/crypto/bcrypt"

	"github.com/vigia/backend/internal/redisstore"
)

var (
	ErrInvalidCredentials = errors.New("credenciales inválidas")
	ErrAccountLocked      = errors.New("cuenta bloqueada temporalmente por intentos fallidos")
	ErrStoreUnavailable   = errors.New("almacén de sesiones no disponible")
)

// Parámetros del bloqueo anti fuerza-bruta de login.
const (
	loginFailThreshold = 5
	loginLockWindow    = 15 * time.Minute
)

// ErrUserNotFound lo devuelve el UserStore cuando no hay coincidencia.
var ErrUserNotFound = errors.New("usuario no encontrado")

// User es la vista mínima de un usuario para autenticación.
type User struct {
	ID           string
	Username     string
	Role         string
	PasswordHash string
}

// UserStore abstrae el acceso al repositorio de usuarios (lo implementa repository).
type UserStore interface {
	GetUserByUsername(ctx context.Context, username string) (User, error)
	GetUserByID(ctx context.Context, id string) (User, error)
}

// TokenPair es lo que se entrega al cliente tras login/refresh.
type TokenPair struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"` // segundos de vida del access token
}

// PublicUser es la información de usuario expuesta al cliente (sin hash).
type PublicUser struct {
	ID       string `json:"id"`
	Username string `json:"username"`
	Role     string `json:"role"`
}

// Service orquesta login, refresh y logout.
type Service struct {
	tokens     *TokenManager
	store      *redisstore.Store
	users      UserStore
	refreshTTL time.Duration
	now        func() time.Time

	// dummyHash es un hash bcrypt REAL de una contraseña aleatoria, generado una sola
	// vez al construir el servicio. No es secreto ni se configura: su único uso es
	// comparar contra él cuando el usuario no existe, para que ese caso tarde lo mismo
	// que una contraseña errónea y no se filtre por temporización qué usuarios existen.
	dummyHash []byte
}

func NewService(tokens *TokenManager, store *redisstore.Store, users UserStore, refreshTTL time.Duration) *Service {
	// Hash de relleno a partir de bytes aleatorios (se descarta la contraseña; nunca se usa).
	filler := make([]byte, 32)
	_, _ = rand.Read(filler)
	dummy, _ := bcrypt.GenerateFromPassword(filler, bcryptCost)

	return &Service{
		tokens:     tokens,
		store:      store,
		users:      users,
		refreshTTL: refreshTTL,
		now:        time.Now,
		dummyHash:  dummy,
	}
}

// loginLockID combina usuario e IP para el contador de fuerza-bruta. Clavar el lockout a
// (usuario, IP) evita un DoS dirigido: un atacante que falle 5 veces solo se bloquea a SÍ
// mismo (su IP), no a la cuenta legítima del usuario desde otra IP. El abuso distribuido se
// acota además con el rate-limit por IP del scope "login".
func loginLockID(username, clientIP string) string {
	if clientIP == "" {
		clientIP = "unknown"
	}
	return username + "|" + clientIP
}

// Login valida credenciales y emite un par de tokens. Aplica bloqueo anti fuerza-bruta
// por (usuario, IP). `clientIP` la provee el handler (ver middleware.ClientIP).
func (s *Service) Login(ctx context.Context, username, password, clientIP string) (TokenPair, PublicUser, error) {
	lockID := loginLockID(username, clientIP)
	if s.store.LoginLocked(ctx, lockID, loginFailThreshold) {
		return TokenPair{}, PublicUser{}, ErrAccountLocked
	}

	u, err := s.users.GetUserByUsername(ctx, username)
	if err != nil {
		// Anti-enumeración: misma rama y coste (un bcrypt real) que una contraseña errónea.
		bcrypt.CompareHashAndPassword(s.dummyHash, []byte(password))
		s.store.IncrLoginFail(ctx, lockID, loginLockWindow)
		return TokenPair{}, PublicUser{}, ErrInvalidCredentials
	}
	if !VerifyPassword(u.PasswordHash, password) {
		s.store.IncrLoginFail(ctx, lockID, loginLockWindow)
		return TokenPair{}, PublicUser{}, ErrInvalidCredentials
	}

	s.store.ResetLoginFail(ctx, lockID)
	pair, err := s.issuePair(ctx, u)
	if err != nil {
		return TokenPair{}, PublicUser{}, err
	}
	return pair, PublicUser{ID: u.ID, Username: u.Username, Role: u.Role}, nil
}

// Refresh rota el par de tokens: valida el refresh, lo invalida y emite uno nuevo.
func (s *Service) Refresh(ctx context.Context, refreshToken string) (TokenPair, error) {
	userID, err := s.store.GetRefresh(ctx, refreshToken)
	if err != nil {
		// Token ausente: expirado, ya rotado (posible reuso) o inválido.
		return TokenPair{}, ErrInvalidCredentials
	}
	// Rotación: el refresh usado se invalida de inmediato (un solo uso).
	_ = s.store.DeleteRefresh(ctx, refreshToken)

	u, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		return TokenPair{}, ErrInvalidCredentials
	}
	return s.issuePair(ctx, u)
}

// Logout revoca el access token (denylist por jti) y el refresh token asociado.
func (s *Service) Logout(ctx context.Context, claims *Claims, refreshToken string) error {
	if refreshToken != "" {
		_ = s.store.DeleteRefresh(ctx, refreshToken)
	}
	if claims != nil && claims.ID != "" && claims.ExpiresAt != nil {
		ttl := time.Until(claims.ExpiresAt.Time)
		_ = s.store.Denylist(ctx, claims.ID, ttl)
	}
	return nil
}

// issuePair firma un access token y crea+almacena un refresh token rotativo.
func (s *Service) issuePair(ctx context.Context, u User) (TokenPair, error) {
	now := s.now()
	access, _, exp, err := s.tokens.Sign(u.ID, u.Username, u.Role, now)
	if err != nil {
		return TokenPair{}, err
	}
	refresh, err := randomToken(32)
	if err != nil {
		return TokenPair{}, err
	}
	if err := s.store.SaveRefresh(ctx, refresh, u.ID, s.refreshTTL); err != nil {
		return TokenPair{}, ErrStoreUnavailable
	}
	return TokenPair{
		AccessToken:  access,
		RefreshToken: refresh,
		TokenType:    "Bearer",
		ExpiresIn:    int(time.Until(exp).Seconds()),
	}, nil
}
