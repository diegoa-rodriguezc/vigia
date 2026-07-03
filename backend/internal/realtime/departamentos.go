package realtime

// deptNombre mapea el código DANE de departamento (2 díg.) a un nombre BUSCABLE en prensa. Se usa
// para acotar la consulta a GDELT por nombre (GDELT no conoce el código DANE). El nombre se elige
// por su forma más habitual en titulares (p. ej. "Bogotá", no "Bogotá, D.C."), y a nivel
// departamental las colisiones son mínimas (por eso la señal es por departamento, no por municipio).
var deptNombre = map[string]string{
	"05": "Antioquia", "08": "Atlántico", "11": "Bogotá", "13": "Bolívar",
	"15": "Boyacá", "17": "Caldas", "18": "Caquetá", "19": "Cauca", "20": "Cesar",
	"23": "Córdoba", "25": "Cundinamarca", "27": "Chocó", "41": "Huila",
	"44": "La Guajira", "47": "Magdalena", "50": "Meta", "52": "Nariño",
	"54": "Norte de Santander", "63": "Quindío", "66": "Risaralda", "68": "Santander",
	"70": "Sucre", "73": "Tolima", "76": "Valle del Cauca", "81": "Arauca",
	"85": "Casanare", "86": "Putumayo", "88": "San Andrés y Providencia",
	"91": "Amazonas", "94": "Guainía", "95": "Guaviare", "97": "Vaupés", "99": "Vichada",
}

// DepartamentoNombre devuelve el nombre buscable de un departamento por su código DANE (2 díg.).
// El segundo valor es false si el código no corresponde a un departamento oficial.
func DepartamentoNombre(cod string) (string, bool) {
	n, ok := deptNombre[cod]
	return n, ok
}
