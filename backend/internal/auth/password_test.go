package auth

import "testing"

func TestValidatePassword(t *testing.T) {
	cases := []struct {
		name string
		pw   string
		ok   bool
	}{
		{"válida fuerte", "Vig1a-Segura!2026", true},
		{"corta", "Ab1!xy", false},
		{"sin mayúscula", "vigia-segura!2026", false},
		{"sin minúscula", "VIGIA-SEGURA!2026", false},
		{"sin dígito", "Vigia-Segura!abcd", false},
		{"sin símbolo", "VigiaSegura12026", false},
		{"común", "password", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := ValidatePassword(c.pw)
			if c.ok && err != nil {
				t.Fatalf("esperaba válida, obtuve error: %v", err)
			}
			if !c.ok && err == nil {
				t.Fatal("esperaba inválida, no hubo error")
			}
		})
	}
}

func TestIsCommonPassword(t *testing.T) {
	if !IsCommonPassword("admin") {
		t.Fatal("'admin' debería ser común")
	}
	if IsCommonPassword("Vig1a-Segura!2026") {
		t.Fatal("una contraseña fuerte no debería marcarse como común")
	}
}
