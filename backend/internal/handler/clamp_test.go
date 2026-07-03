package handler

import "testing"

func TestClampInt(t *testing.T) {
	cases := []struct{ n, lo, hi, want int }{
		{5, 1, 24, 5},     // dentro del rango
		{0, 1, 24, 1},     // por debajo → lo
		{1000, 1, 24, 24}, // por encima → hi
		{24, 1, 24, 24},   // en el borde
	}
	for _, c := range cases {
		if got := clampInt(c.n, c.lo, c.hi); got != c.want {
			t.Errorf("clampInt(%d,%d,%d)=%d, quería %d", c.n, c.lo, c.hi, got, c.want)
		}
	}
}

func TestClampFloat(t *testing.T) {
	cases := []struct{ f, lo, hi, want float64 }{
		{0, -100, 100, 0},       // dentro
		{-500, -100, 100, -100}, // por debajo → lo
		{9999, -90, 1000, 1000}, // por encima → hi
	}
	for _, c := range cases {
		if got := clampFloat(c.f, c.lo, c.hi); got != c.want {
			t.Errorf("clampFloat(%v,%v,%v)=%v, quería %v", c.f, c.lo, c.hi, got, c.want)
		}
	}
}
