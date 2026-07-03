package config

import "testing"

func TestInsecureDefaults(t *testing.T) {
	// Todo en su valor público por defecto → ambos secretos flagueados.
	both := InsecureDefaults(Config{JWTSecret: defaultDevSecret, AdminPassword: defaultAdminPassword})
	if len(both) != 2 {
		t.Fatalf("con ambos por defecto esperaba 2 problemas, obtuve %d: %v", len(both), both)
	}

	// Credenciales propias fuertes → sin problemas.
	if got := InsecureDefaults(Config{
		JWTSecret:     "un-secreto-propio-largo-y-aleatorio-xyz-123",
		AdminPassword: "Otr4.Clave.Propia!",
	}); len(got) != 0 {
		t.Fatalf("con credenciales propias esperaba 0 problemas, obtuve %v", got)
	}

	// JWT vacío → flagueado (aunque la contraseña sea propia).
	if got := InsecureDefaults(Config{JWTSecret: "", AdminPassword: "Otr4.Clave.Propia!"}); len(got) != 1 {
		t.Fatalf("con JWT vacío esperaba 1 problema, obtuve %v", got)
	}

	// Solo la contraseña de demo (JWT propio) → un problema.
	if got := InsecureDefaults(Config{
		JWTSecret:     "un-secreto-propio-largo-y-aleatorio-xyz-123",
		AdminPassword: defaultAdminPassword,
	}); len(got) != 1 {
		t.Fatalf("con ADMIN_PASSWORD de demo esperaba 1 problema, obtuve %v", got)
	}
}
