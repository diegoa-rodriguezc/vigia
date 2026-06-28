package auth

import (
	"errors"
	"unicode"

	"golang.org/x/crypto/bcrypt"
)

// bcryptCost equilibra coste de cómputo y seguridad (≈ 12 es el estándar recomendado).
const bcryptCost = 12

const (
	minPasswordLen = 12
	maxPasswordLen = 128
)

// commonPasswords es una lista corta de contraseñas notoriamente débiles que se rechazan
// aunque cumplan la complejidad mínima.
var commonPasswords = map[string]struct{}{
	"password": {}, "contrasena": {}, "contraseña": {}, "admin": {}, "administrator": {},
	"123456": {}, "12345678": {}, "123456789": {}, "1234567890": {}, "qwerty": {},
	"abc123": {}, "111111": {}, "iloveyou": {}, "welcome": {}, "letmein": {},
	"changeme": {}, "cambiame": {}, "secret": {}, "vigia": {}, "vigia123": {},
}

// HashPassword devuelve el hash bcrypt de una contraseña en claro.
func HashPassword(pw string) (string, error) {
	b, err := bcrypt.GenerateFromPassword([]byte(pw), bcryptCost)
	return string(b), err
}

// VerifyPassword compara una contraseña en claro contra su hash bcrypt (tiempo constante).
func VerifyPassword(hash, pw string) bool {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(pw)) == nil
}

// IsCommonPassword indica si la contraseña está en la lista de contraseñas débiles comunes.
func IsCommonPassword(pw string) bool {
	_, ok := commonPasswords[pw]
	return ok
}

// ValidatePassword aplica la política de contraseñas: longitud 12–128 y al menos una
// mayúscula, una minúscula, un dígito y un símbolo; rechaza contraseñas comunes. Se usa al
// crear/insertar usuarios (no en el login, que valida contra el hash existente).
func ValidatePassword(pw string) error {
	if len(pw) < minPasswordLen {
		return errors.New("la contraseña debe tener al menos 12 caracteres")
	}
	if len(pw) > maxPasswordLen {
		return errors.New("la contraseña no debe superar 128 caracteres")
	}
	if IsCommonPassword(pw) {
		return errors.New("la contraseña es demasiado común")
	}
	var hasUpper, hasLower, hasDigit, hasSymbol bool
	for _, c := range pw {
		switch {
		case unicode.IsUpper(c):
			hasUpper = true
		case unicode.IsLower(c):
			hasLower = true
		case unicode.IsDigit(c):
			hasDigit = true
		case unicode.IsPunct(c) || unicode.IsSymbol(c):
			hasSymbol = true
		}
	}
	if !hasUpper || !hasLower || !hasDigit || !hasSymbol {
		return errors.New("la contraseña debe incluir mayúscula, minúscula, dígito y símbolo")
	}
	return nil
}
