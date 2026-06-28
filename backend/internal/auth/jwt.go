// Package auth implementa la autenticación de la API: JWT (access), refresh tokens
// rotativos en Redis, hashing de contraseñas y middleware de protección de rutas.
package auth

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	issuer   = "vigia"
	audience = "vigia-api"
)

var (
	ErrInvalidToken = errors.New("token inválido")
	ErrExpired      = errors.New("token expirado")
)

// Claims son los datos firmados dentro del access token.
type Claims struct {
	Username string `json:"username"`
	Role     string `json:"role"`
	jwt.RegisteredClaims
}

// TokenManager firma y valida access tokens HS256.
type TokenManager struct {
	secret     []byte
	expiration time.Duration
}

func NewTokenManager(secret string, expiration time.Duration) *TokenManager {
	return &TokenManager{secret: []byte(secret), expiration: expiration}
}

// Sign emite un access token para un usuario. Devuelve el token, su jti y su expiración.
func (m *TokenManager) Sign(userID, username, role string, now time.Time) (token, jti string, exp time.Time, err error) {
	jti, err = randomToken(16)
	if err != nil {
		return "", "", time.Time{}, err
	}
	exp = now.Add(m.expiration)
	claims := Claims{
		Username: username,
		Role:     role,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			Issuer:    issuer,
			Audience:  jwt.ClaimStrings{audience},
			IssuedAt:  jwt.NewNumericDate(now),
			NotBefore: jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(exp),
			ID:        jti,
		},
	}
	t := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := t.SignedString(m.secret)
	return signed, jti, exp, err
}

// Parse valida la firma (HS256 pineado), el emisor, la audiencia y la expiración.
func (m *TokenManager) Parse(token string) (*Claims, error) {
	claims := &Claims{}
	parsed, err := jwt.ParseWithClaims(token, claims, func(t *jwt.Token) (any, error) {
		// Pinning del algoritmo: rechaza `alg:none` o cualquier método distinto de HS256.
		if t.Method != jwt.SigningMethodHS256 {
			return nil, ErrInvalidToken
		}
		return m.secret, nil
	},
		jwt.WithIssuer(issuer),
		jwt.WithAudience(audience),
		jwt.WithLeeway(30*time.Second), // tolerancia de reloj
	)
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrExpired
		}
		return nil, ErrInvalidToken
	}
	if !parsed.Valid {
		return nil, ErrInvalidToken
	}
	return claims, nil
}

// randomToken genera n bytes aleatorios y los codifica en base64url (sin padding).
// Se usa para los jti y para los refresh tokens opacos.
func randomToken(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}
