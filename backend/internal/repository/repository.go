// Package repository accede a las tablas gold en PostgreSQL que expone la API.
package repository

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrNoDB           = errors.New("base de datos no disponible")
	ErrNotInitialized = errors.New("base de datos sin inicializar: ejecuta el pipeline")
)

// mapErr traduce el error de tabla inexistente (42P01) a un error de negocio claro,
// que el handler convierte en 503 con un mensaje accionable en vez de un 500 con SQL crudo.
func mapErr(err error) error {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "42P01" {
		return ErrNotInitialized
	}
	return err
}

type Repository struct {
	pool *pgxpool.Pool
}

// New crea un pool de conexiones. Devuelve error si no logra conectar.
func New(ctx context.Context, dsn string) (*Repository, error) {
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	return &Repository{pool: pool}, nil
}

func (r *Repository) Close() {
	if r != nil && r.pool != nil {
		r.pool.Close()
	}
}

// MunicipioResumen es un KPI agregado por municipio. `total_hechos` es el gran total;
// `total_delitos` es la incidencia delictiva (lo que se quiere prevenir) y
// `total_respuestas` la actividad institucional (capturas/incautaciones/recuperaciones).
type MunicipioResumen struct {
	CodMunicipio    string   `json:"cod_municipio"`
	Municipio       string   `json:"municipio"`
	Departamento    string   `json:"departamento"`
	TotalHechos     int64    `json:"total_hechos"`
	TotalDelitos    int64    `json:"total_delitos"`
	TotalRespuestas int64    `json:"total_respuestas"`
	Categorias      int      `json:"categorias"`
	Lat             *float64 `json:"lat"`
	Lon             *float64 `json:"lon"`
}

// SeriePunto es un punto de la serie mensual.
type SeriePunto struct {
	Periodo  string `json:"periodo"`
	Cantidad int64  `json:"cantidad"`
}

// Anomalia es una alerta temprana detectada.
type Anomalia struct {
	CodMunicipio string  `json:"cod_municipio"`
	Municipio    string  `json:"municipio"`
	Departamento string  `json:"departamento"`
	Categoria    string  `json:"categoria"`
	Periodo      string  `json:"periodo"`
	Cantidad     int64   `json:"cantidad"`
	ScoreZ       float64 `json:"score_z"`
	Severidad    string  `json:"severidad"`
}

func (r *Repository) Available() bool { return r != nil && r.pool != nil }

// Ping verifica la conectividad REAL con la base de datos (no solo que el pool exista). Lo usa
// la sonda de readiness para distinguir "BD inalcanzable" (no listo) de "BD accesible pero sin
// poblar" (listo: los endpoints de datos devuelven 503 accionable, pero la conexión está viva).
func (r *Repository) Ping(ctx context.Context) error {
	if !r.Available() {
		return ErrNoDB
	}
	return r.pool.Ping(ctx)
}

// TopMunicipios devuelve los municipios con mayor número de hechos.
func (r *Repository) TopMunicipios(ctx context.Context, limit int) ([]MunicipioResumen, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT cod_municipio, municipio, departamento,
		        total_hechos,
		        coalesce(total_delitos, total_hechos) AS total_delitos,
		        coalesce(total_respuestas, 0)         AS total_respuestas,
		        categorias, lat, lon
		 FROM resumen_municipio
		 ORDER BY coalesce(total_delitos, total_hechos) DESC LIMIT $1`, limit)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()

	out := []MunicipioResumen{}
	for rows.Next() {
		var m MunicipioResumen
		if err := rows.Scan(&m.CodMunicipio, &m.Municipio, &m.Departamento,
			&m.TotalHechos, &m.TotalDelitos, &m.TotalRespuestas, &m.Categorias, &m.Lat, &m.Lon); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, mapErr(rows.Err())
}

// MunicipioRef es la referencia mínima de un municipio para selectores.
type MunicipioRef struct {
	CodMunicipio string `json:"cod_municipio"`
	Municipio    string `json:"municipio"`
	Departamento string `json:"departamento"`
}

// Municipios devuelve TODOS los municipios ordenados alfabéticamente (para el selector).
func (r *Repository) Municipios(ctx context.Context) ([]MunicipioRef, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT cod_municipio, municipio, departamento
		 FROM resumen_municipio ORDER BY municipio`)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()

	out := []MunicipioRef{}
	for rows.Next() {
		var m MunicipioRef
		if err := rows.Scan(&m.CodMunicipio, &m.Municipio, &m.Departamento); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, mapErr(rows.Err())
}

// Stats son los totales globales para las tarjetas KPI del tablero.
type Stats struct {
	Municipios      int    `json:"municipios"`
	Departamentos   int    `json:"departamentos"`
	Categorias      int    `json:"categorias"`
	TotalHechos     int64  `json:"total_hechos"`
	TotalDelitos    int64  `json:"total_delitos"`
	TotalRespuestas int64  `json:"total_respuestas"`
	Anomalias       int    `json:"anomalias"`
	AnomaliasAlta   int    `json:"anomalias_alta"`
	AnomaliasMedia  int    `json:"anomalias_media"`
	PeriodoMin      string `json:"periodo_min"`
	PeriodoMax      string `json:"periodo_max"`
}

// GetStats calcula los totales reales con COUNT/SUM (no limitados por paginación),
// para que los KPIs del tablero no dependan del tamaño del fetch.
func (r *Repository) GetStats(ctx context.Context) (*Stats, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	var s Stats
	err := r.pool.QueryRow(ctx, `
		SELECT
			rm.total_municipio,
			rm.total_departamentos,
			c.categorias,
			rm.total_hechos,
			rm.total_delitos,
			rm.total_respuestas,
			a.total, 
			a.alta, 
			a.media,
			sm.pmin, 
			sm.pmax
		FROM (
			SELECT
				count(1) AS total_municipio,
				count(DISTINCT substr(cod_municipio, 1, 2)) AS total_departamentos,
				coalesce(sum(total_hechos), 0) AS total_hechos,
				coalesce(sum(coalesce(total_delitos, total_hechos)), 0) AS total_delitos,
				coalesce(sum(coalesce(total_respuestas, 0)), 0) total_respuestas
			FROM resumen_municipio
		) rm
		CROSS JOIN
		(
			SELECT 
				count(1) AS total,
			    count(1) FILTER (WHERE severidad = 'ALTA') AS alta,
			    count(1) FILTER (WHERE severidad = 'MEDIA') AS media
			FROM anomalias
		) a
		CROSS JOIN (
			SELECT 
				count(DISTINCT categoria) AS categorias
    		FROM serie_mensual
    		WHERE naturaleza = 'delito'
		) c
		CROSS JOIN
		(
			SELECT 
				coalesce(to_char(min(periodo), 'YYYY-MM'), '') AS pmin,
			    coalesce(to_char(max(periodo), 'YYYY-MM'), '') AS pmax
			FROM serie_mensual
		) sm
	`).Scan(&s.Municipios, &s.Departamentos, &s.Categorias, &s.TotalHechos,
		&s.TotalDelitos, &s.TotalRespuestas,
		&s.Anomalias, &s.AnomaliasAlta, &s.AnomaliasMedia, &s.PeriodoMin, &s.PeriodoMax)
	if err != nil {
		return nil, mapErr(err)
	}
	return &s, nil
}

// DepartamentoResumen agrega la incidencia por departamento (para el mapa de calor).
type DepartamentoResumen struct {
	CodDepartamento string `json:"cod_departamento"`
	Departamento    string `json:"departamento"`
	// TotalDelitos: el mapa representa INCIDENCIA DELICTIVA (no el gran total, que
	// incluiría capturas/incautaciones/recuperaciones). Ver la consulta abajo.
	TotalDelitos int64 `json:"total_delitos"`
	Municipios   int   `json:"municipios"`
}

// Departamentos agrega resumen_municipio por código DANE de departamento
// (los 2 primeros dígitos del código de municipio) para la coropleta.
func (r *Repository) Departamentos(ctx context.Context) ([]DepartamentoResumen, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	// El mapa de calor representa INCIDENCIA DELICTIVA: agrega total_delitos (no el gran
	// total, que incluiría capturas/incautaciones/recuperaciones).
	rows, err := r.pool.Query(ctx,
		`SELECT substr(cod_municipio, 1, 2)              AS cod_dpto,
		        min(departamento)                        AS departamento,
		        sum(coalesce(total_delitos, total_hechos)) AS total,
		        count(1)                                 AS municipios
		 FROM resumen_municipio
		 WHERE cod_municipio IS NOT NULL
		 GROUP BY substr(cod_municipio, 1, 2)
		 ORDER BY total DESC`)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()

	out := []DepartamentoResumen{}
	for rows.Next() {
		var d DepartamentoResumen
		if err := rows.Scan(&d.CodDepartamento, &d.Departamento, &d.TotalDelitos, &d.Municipios); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, mapErr(rows.Err())
}

// Categorias devuelve las categorías de delito (orden alfabético). Si se pasa
// codMunicipio, solo devuelve las que TIENEN historial en ese municipio, para que el
// tablero no ofrezca combinaciones municipio×categoría sin datos (que darían 404).
func (r *Repository) Categorias(ctx context.Context, codMunicipio string) ([]string, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	query := `SELECT categoria FROM serie_mensual `
	args := []any{}
	if codMunicipio != "" {
		query += `WHERE cod_municipio = $1 `
		args = append(args, codMunicipio)
	}
	query += `GROUP BY categoria ORDER BY categoria`
	rows, err := r.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()

	out := []string{}
	for rows.Next() {
		var c string
		if err := rows.Scan(&c); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, mapErr(rows.Err())
}

// TimeSeries devuelve la serie mensual de un municipio y categoría.
func (r *Repository) TimeSeries(ctx context.Context, codMunicipio, categoria string) ([]SeriePunto, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT to_char(periodo, 'YYYY-MM') AS periodo, cantidad
		 FROM   serie_mensual 
		 WHERE  cod_municipio = $1 
		 AND    categoria = $2 
		 ORDER  BY periodo`,
		codMunicipio, categoria)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()

	out := []SeriePunto{}
	for rows.Next() {
		var p SeriePunto
		if err := rows.Scan(&p.Periodo, &p.Cantidad); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, mapErr(rows.Err())
}

// CategoriaTotal es el total de hechos de una categoría en un municipio (para el drill-down).
type CategoriaTotal struct {
	Categoria  string `json:"categoria"`
	Naturaleza string `json:"naturaleza"` // "delito" | "respuesta"
	Total      int64  `json:"total"`
}

// MunicipioDetalle devuelve el desglose por categoría de un municipio (mayor a menor),
// separando delito de respuesta institucional. Alimenta el drill-down del tablero.
func (r *Repository) MunicipioDetalle(ctx context.Context, codMunicipio string) ([]CategoriaTotal, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT categoria, naturaleza, sum(cantidad) AS total
		 FROM   serie_mensual
		 WHERE  cod_municipio = $1
		 GROUP  BY categoria, naturaleza
		 ORDER  BY total DESC`,
		codMunicipio)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()

	out := []CategoriaTotal{}
	for rows.Next() {
		var c CategoriaTotal
		if err := rows.Scan(&c.Categoria, &c.Naturaleza, &c.Total); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, mapErr(rows.Err())
}

// AnomaliaQuery describe una página de alertas (filtro + orden + paginación).
type AnomaliaQuery struct {
	Limit, Offset int
	Severidad     string // "", "ALTA", "MEDIA"
	Search        string // texto libre (municipio/departamento/categoría)
	Sort          string // columna (whitelisted); por defecto "periodo"
	Dir           string // "asc" | "desc"
}

// Columnas permitidas para ordenar (whitelist: evita inyección por la query string).
var anomaliaSortCols = map[string]string{
	"periodo": "periodo", "municipio": "municipio", "departamento": "departamento",
	"categoria": "categoria", "cantidad": "cantidad", "score_z": "score_z", "severidad": "severidad",
}

// Normaliza el texto de búsqueda (minúsculas + sin tildes) para casar contra los
// nombres oficiales DANE, que SÍ llevan tilde ('BOGOTÁ, D.C.'). En SQL se aplica el
// equivalente con translate(lower(col), ...).
var accentRepl = strings.NewReplacer(
	"á", "a", "é", "e", "í", "i", "ó", "o", "ú", "u", "ü", "u", "ñ", "n",
	"Á", "a", "É", "e", "Í", "i", "Ó", "o", "Ú", "u", "Ü", "u", "Ñ", "n",
)

func normSearch(s string) string { return accentRepl.Replace(strings.ToLower(strings.TrimSpace(s))) }

// unaccentLower es la expresión SQL espejo de normSearch para una columna.
func unaccentLower(col string) string {
	return "translate(lower(" + col + "), 'áéíóúüñ', 'aeiouun')"
}

// Anomalias devuelve una página de alertas según el filtro/orden, y el total que
// cumple el filtro (para la paginación de servidor). La inyección se evita usando
// argumentos posicionales y una whitelist para la columna de orden.
func (r *Repository) Anomalias(ctx context.Context, q AnomaliaQuery) ([]Anomalia, int, error) {
	if !r.Available() {
		return nil, 0, ErrNoDB
	}

	where := "WHERE 1=1"
	args := []any{}
	i := 1
	if q.Severidad == "ALTA" || q.Severidad == "MEDIA" {
		where += fmt.Sprintf(" AND severidad = $%d", i)
		args = append(args, q.Severidad)
		i++
	}
	if s := normSearch(q.Search); s != "" {
		where += fmt.Sprintf(" AND (%s LIKE $%d OR %s LIKE $%d OR %s LIKE $%d)",
			unaccentLower("municipio"), i, unaccentLower("departamento"), i, unaccentLower("categoria"), i)
		args = append(args, "%"+s+"%")
		i++
	}

	var total int
	if err := r.pool.QueryRow(ctx, "SELECT count(1) FROM anomalias "+where, args...).Scan(&total); err != nil {
		return nil, 0, mapErr(err)
	}

	sortCol := anomaliaSortCols[q.Sort]
	if sortCol == "" {
		sortCol = "periodo"
	}
	dir := "DESC"
	if strings.EqualFold(q.Dir, "asc") {
		dir = "ASC"
	}
	// Desempate estable (periodo, cod_municipio) para que la paginación no repita/salte filas.
	sql := fmt.Sprintf(
		`SELECT cod_municipio, municipio, departamento, categoria,
		        to_char(periodo, 'YYYY-MM') AS periodo, cantidad, score_z, severidad
		 FROM anomalias %s ORDER BY %s %s, periodo DESC, cod_municipio LIMIT $%d OFFSET $%d`,
		where, sortCol, dir, i, i+1)
	args = append(args, q.Limit, q.Offset)

	rows, err := r.pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, 0, mapErr(err)
	}
	defer rows.Close()

	out := []Anomalia{}
	for rows.Next() {
		var a Anomalia
		if err := rows.Scan(&a.CodMunicipio, &a.Municipio, &a.Departamento, &a.Categoria,
			&a.Periodo, &a.Cantidad, &a.ScoreZ, &a.Severidad); err != nil {
			return nil, 0, err
		}
		out = append(out, a)
	}
	return out, total, mapErr(rows.Err())
}

// ───────────────────────── Capa "Justicia" (Fiscalía) ─────────────────────────
// Tablas justicia_resumen (por municipio) y justicia_anual (municipio×año×etapa). Mide el
// EMBUDO DE JUDICIALIZACIÓN: qué fracción de las noticias criminales supera la indagación.

// JusticiaEtapa es un escalón del embudo nacional (etapa cruda + su clase).
type JusticiaEtapa struct {
	Etapa     string `json:"etapa"`
	Clase     string `json:"clase_etapa"` // indagacion | judicializado | desconocido
	NProcesos int64  `json:"n_procesos"`
}

// JusticiaResumenNacional es el embudo nacional + KPIs.
type JusticiaResumenNacional struct {
	TotalProcesos       int64           `json:"total_procesos"`
	TotalJudicializados int64           `json:"total_judicializados"`
	TotalEtapaConocida  int64           `json:"total_etapa_conocida"`
	TasaJudicializacion float64         `json:"tasa_judicializacion_pct"`
	Municipios          int             `json:"municipios"`
	Embudo              []JusticiaEtapa `json:"embudo"`
}

// JusticiaResumen devuelve el embudo nacional (por etapa) y los KPIs de judicialización.
func (r *Repository) JusticiaResumen(ctx context.Context) (*JusticiaResumenNacional, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	var jr JusticiaResumenNacional
	if err := r.pool.QueryRow(ctx,
		`SELECT coalesce(sum(total_procesos), 0), coalesce(sum(n_judicializados), 0),
		        coalesce(sum(procesos_etapa_conocida), 0), count(1)
		 FROM justicia_resumen`).Scan(
		&jr.TotalProcesos, &jr.TotalJudicializados, &jr.TotalEtapaConocida, &jr.Municipios); err != nil {
		return nil, mapErr(err)
	}
	if jr.TotalEtapaConocida > 0 {
		jr.TasaJudicializacion = 100 * float64(jr.TotalJudicializados) / float64(jr.TotalEtapaConocida)
	}
	// Embudo nacional por etapa cruda (la clase es función de la etapa → max() la selecciona).
	rows, err := r.pool.Query(ctx,
		`SELECT etapa, max(clase_etapa) AS clase, sum(n_procesos) AS n
		 FROM justicia_anual
		 GROUP BY etapa
		 ORDER BY n DESC`)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()
	jr.Embudo = []JusticiaEtapa{}
	for rows.Next() {
		var e JusticiaEtapa
		if err := rows.Scan(&e.Etapa, &e.Clase, &e.NProcesos); err != nil {
			return nil, err
		}
		jr.Embudo = append(jr.Embudo, e)
	}
	return &jr, mapErr(rows.Err())
}

// JusticiaMunicipio es la fila del ranking por municipio.
type JusticiaMunicipio struct {
	CodMunicipio        string  `json:"cod_municipio"`
	Municipio           string  `json:"municipio"`
	Departamento        string  `json:"departamento"`
	TotalProcesos       int64   `json:"total_procesos"`
	NJudicializados     int64   `json:"n_judicializados"`
	TasaJudicializacion float64 `json:"tasa_judicializacion_pct"`
}

// JusticiaMunicipios devuelve el ranking de municipios por volumen de procesos (con su tasa).
func (r *Repository) JusticiaMunicipios(ctx context.Context) ([]JusticiaMunicipio, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	// COALESCE: unos pocos códigos DANE no cruzan con DIVIPOLA (extranjeros/sin dato) y traen
	// municipio/departamento NULL → se rotulan con el código para no romper el scan a string.
	rows, err := r.pool.Query(ctx,
		`SELECT cod_municipio, coalesce(municipio, cod_municipio), coalesce(departamento, '—'),
		        total_procesos, n_judicializados, tasa_judicializacion_pct
		 FROM justicia_resumen
		 ORDER BY total_procesos DESC`)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()
	out := []JusticiaMunicipio{}
	for rows.Next() {
		var m JusticiaMunicipio
		if err := rows.Scan(&m.CodMunicipio, &m.Municipio, &m.Departamento,
			&m.TotalProcesos, &m.NJudicializados, &m.TasaJudicializacion); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, mapErr(rows.Err())
}

// JusticiaDelito es la fila del ranking nacional por título del Código Penal.
type JusticiaDelito struct {
	TituloDelito          string  `json:"titulo_delito"`
	TotalProcesos         int64   `json:"total_procesos"`
	NJudicializados       int64   `json:"n_judicializados"`
	ProcesosEtapaConocida int64   `json:"procesos_etapa_conocida"`
	TasaJudicializacion   float64 `json:"tasa_judicializacion_pct"`
}

// JusticiaDelitos devuelve la tasa de judicialización NACIONAL por título del Código Penal
// (taxonomía propia de la Fiscalía, ~30 filas), ordenada por volumen de procesos.
func (r *Repository) JusticiaDelitos(ctx context.Context) ([]JusticiaDelito, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT titulo_delito, total_procesos, n_judicializados,
		        procesos_etapa_conocida, tasa_judicializacion_pct
		 FROM justicia_delito
		 ORDER BY total_procesos DESC`)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()
	out := []JusticiaDelito{}
	for rows.Next() {
		var d JusticiaDelito
		if err := rows.Scan(&d.TituloDelito, &d.TotalProcesos, &d.NJudicializados,
			&d.ProcesosEtapaConocida, &d.TasaJudicializacion); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, mapErr(rows.Err())
}

// JusticiaDepartamento agrega la tasa de judicialización por departamento (para la coropleta).
type JusticiaDepartamento struct {
	CodDepartamento     string  `json:"cod_departamento"`
	Departamento        string  `json:"departamento"`
	TotalProcesos       int64   `json:"total_procesos"`
	NJudicializados     int64   `json:"n_judicializados"`
	TasaJudicializacion float64 `json:"tasa_judicializacion_pct"`
	Municipios          int     `json:"municipios"`
}

// JusticiaDepartamentos agrega justicia_resumen por código DANE de departamento (2 primeros
// dígitos del municipio). La tasa es sum(judicializados)/sum(etapa conocida) — NO un promedio de
// tasas municipales (que sobreponderaría municipios pequeños).
func (r *Repository) JusticiaDepartamentos(ctx context.Context) ([]JusticiaDepartamento, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT substr(cod_municipio, 1, 2)        AS cod_dpto,
		        coalesce(min(departamento), '—')   AS departamento,
		        sum(total_procesos)                AS procesos,
		        sum(n_judicializados)              AS judic,
		        sum(procesos_etapa_conocida)       AS conocida,
		        count(1)                           AS municipios
		 FROM justicia_resumen
		 WHERE cod_municipio IS NOT NULL
		 GROUP BY substr(cod_municipio, 1, 2)
		 ORDER BY procesos DESC`)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()
	out := []JusticiaDepartamento{}
	for rows.Next() {
		var d JusticiaDepartamento
		var conocida int64
		if err := rows.Scan(&d.CodDepartamento, &d.Departamento, &d.TotalProcesos,
			&d.NJudicializados, &conocida, &d.Municipios); err != nil {
			return nil, err
		}
		if conocida > 0 {
			d.TasaJudicializacion = 100 * float64(d.NJudicializados) / float64(conocida)
		}
		out = append(out, d)
	}
	return out, mapErr(rows.Err())
}

// JusticiaEtapaAnual es una fila del drill-down por municipio (año × etapa).
type JusticiaEtapaAnual struct {
	Anio      int    `json:"anio"`
	Etapa     string `json:"etapa"`
	Clase     string `json:"clase_etapa"`
	NProcesos int64  `json:"n_procesos"`
}

// JusticiaMunicipioDetalle devuelve el desglose año×etapa de un municipio (drill-down).
func (r *Repository) JusticiaMunicipioDetalle(ctx context.Context, codMunicipio string) ([]JusticiaEtapaAnual, error) {
	if !r.Available() {
		return nil, ErrNoDB
	}
	rows, err := r.pool.Query(ctx,
		`SELECT anio, etapa, clase_etapa, n_procesos
		 FROM justicia_anual
		 WHERE cod_municipio = $1
		 ORDER BY anio, etapa`, codMunicipio)
	if err != nil {
		return nil, mapErr(err)
	}
	defer rows.Close()
	out := []JusticiaEtapaAnual{}
	for rows.Next() {
		var e JusticiaEtapaAnual
		if err := rows.Scan(&e.Anio, &e.Etapa, &e.Clase, &e.NProcesos); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, mapErr(rows.Err())
}
