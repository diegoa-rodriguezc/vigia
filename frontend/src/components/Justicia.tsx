import { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, Cell, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import {
  getJusticiaResumen, getJusticiaMunicipios, getJusticiaDepartamentos,
  type JusticiaResumenNacional, type JusticiaMunicipio, type JusticiaDepartamento,
} from "../api";
import { StatTile, SkeletonRows, Pagination, ExportButton, ChartTooltip, usePagination, nfmt } from "./ui";
import { Icon } from "./icons";

// Orden canónico de la cadena penal (Indagación → … → Ejecución), independiente del conteo,
// para que el embudo se lea como una secuencia y no por volumen.
const ORDEN_ETAPA: Record<string, number> = {
  indagación: 0, investigación: 1, juicio: 2, "ejecución de penas": 3,
};
const ordenDe = (etapa: string) => ORDEN_ETAPA[etapa.toLowerCase()] ?? 9;

// Color por clase: indagación = ámbar (estancado), judicializado = azul/verde (avanzó).
const COLOR_CLASE: Record<string, string> = {
  indagacion: "#fbbf24",
  judicializado: "#38bdf8",
  desconocido: "#475569",
};
const colorEtapa = (etapa: string, clase: string) =>
  etapa.toLowerCase() === "ejecución de penas" ? "#22c55e" : (COLOR_CLASE[clase] ?? "#475569");

const pct = (n: number) => `${n.toFixed(2)}%`;

type SortKey = "municipio" | "departamento" | "total_procesos" | "n_judicializados" | "tasa_judicializacion_pct";

// `aria-sort` para la cabecera de la columna activa (lectores de pantalla).
const ariaSort = (active: boolean, dir: "asc" | "desc"): "ascending" | "descending" | undefined =>
  active ? (dir === "asc" ? "ascending" : "descending") : undefined;

export default function Justicia() {
  const [resumen, setResumen] = useState<JusticiaResumenNacional | null>(null);
  const [municipios, setMunicipios] = useState<JusticiaMunicipio[]>([]);
  const [departamentos, setDepartamentos] = useState<JusticiaDepartamento[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("total_procesos");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    let alive = true;
    Promise.all([
      getJusticiaResumen().then((d) => { if (alive) setResumen(d); }),
      getJusticiaMunicipios().then((d) => { if (alive) setMunicipios(d); }),
      getJusticiaDepartamentos().then((d) => { if (alive) setDepartamentos(d); }),
    ])
      .catch((e) => { if (alive) setError(e?.response?.data?.error ?? e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  // Embudo nacional ordenado por la secuencia penal (no por volumen).
  const embudo = useMemo(() => {
    if (!resumen) return [];
    return [...resumen.embudo]
      .sort((a, b) => ordenDe(a.etapa) - ordenDe(b.etapa))
      .map((e) => ({ etapa: e.etapa, n: e.n_procesos, clase: e.clase_etapa }));
  }, [resumen]);

  // Top departamentos por tasa de judicialización (los que tienen ≥ 5.000 procesos, para
  // que la tasa sea estable y no la dominen departamentos diminutos).
  const topDeptos = useMemo(() => {
    return [...departamentos]
      .filter((d) => d.total_procesos >= 5000)
      .sort((a, b) => b.tasa_judicializacion_pct - a.tasa_judicializacion_pct)
      .slice(0, 12)
      .map((d) => ({ name: d.departamento, tasa: d.tasa_judicializacion_pct }));
  }, [departamentos]);

  // Ranking de municipios filtrado + ordenado (cliente) + paginación.
  const vista = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    const filtrada = q
      ? municipios.filter((m) =>
          m.municipio.toLowerCase().includes(q) || m.departamento.toLowerCase().includes(q))
      : municipios;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtrada].sort((a, b) => {
      const cmp = (sortKey === "municipio" || sortKey === "departamento")
        ? a[sortKey].localeCompare(b[sortKey], "es")
        : a[sortKey] - b[sortKey];
      return cmp * dir;
    });
  }, [municipios, filtro, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "municipio" || key === "departamento" ? "asc" : "desc"); }
  };
  const arrow = (key: SortKey) =>
    sortKey === key ? <span className="arrow"> {sortDir === "asc" ? "▲" : "▼"}</span> : null;

  const pg = usePagination(vista, 10, `${filtro}|${sortKey}|${sortDir}`);

  if (error) return (
    <div className="empty-state" role="alert">
      <span className="empty-ic"><Icon name="inbox" size={28} /></span>
      No hay datos de Justicia todavía: {error}
    </div>
  );

  return (
    <>
      <h2 className="section-title">Justicia</h2>
      <p className="section-sub">
        Embudo de judicialización de la <b>Fiscalía General de la Nación</b> (≈23 millones de procesos): qué
        fracción de las noticias criminales supera la indagación y avanza en la cadena penal.
      </p>
      <p className="section-sub" style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
        <Icon name="info" size={13} />
        <span>
          Capa <b>paralela</b> a los delitos de la Policía (un <i>proceso</i> no es un <i>hecho registrado</i>:
          no son comparables 1:1). El volumen lo domina la <b>indagación</b>, por eso el indicador clave es la
          <b> tasa de judicialización</b> (sobre etapas conocidas), no el conteo bruto. Los años recientes
          subcuentan por el <b>rezago judicial</b>.
        </span>
      </p>

      <div className="kpis">
        <StatTile icon={<Icon name="layers" />} label="Procesos totales" loading={loading}
          value={nfmt(resumen?.total_procesos ?? 0)} hint="Fiscalía · 2004-2026" />
        <StatTile icon={<Icon name="trending-up" />} tone="danger" label="Tasa de judicialización" loading={loading}
          value={resumen ? pct(resumen.tasa_judicializacion_pct) : "—"} hint="superan la indagación (nacional)" />
        <StatTile icon={<Icon name="award" />} label="Procesos judicializados" loading={loading}
          value={nfmt(resumen?.total_judicializados ?? 0)} hint="investigación, juicio o ejecución" />
        <StatTile icon={<Icon name="map-pin" />} label="Municipios cubiertos" loading={loading}
          value={nfmt(resumen?.municipios ?? 0)} hint="con al menos un proceso" />
      </div>

      <div className="card">
        <h3><Icon name="bar-chart" /> Embudo de judicialización (nacional)</h3>
        <p className="card-sub">
          Procesos por etapa de la cadena penal. La indagación concentra la gran mayoría; solo una fracción
          avanza a investigación, juicio o ejecución de penas.
        </p>
        {loading ? <div className="skeleton" style={{ height: 240 }} /> : (
          <ResponsiveContainer width="100%" height={Math.max(220, embudo.length * 48)}>
            <BarChart data={embudo} layout="vertical" margin={{ left: 8, right: 24 }}>
              <XAxis type="number" stroke="#94a3b8" fontSize={11}
                tickFormatter={(v) => nfmt(v as number)} />
              <YAxis type="category" dataKey="etapa" width={130} stroke="#94a3b8" fontSize={12} />
              <RTooltip cursor={{ fill: "rgba(56,189,248,0.08)" }} content={<ChartTooltip />} />
              <Bar dataKey="n" name="Procesos" radius={[0, 4, 4, 0]}>
                {embudo.map((e) => <Cell key={e.etapa} fill={colorEtapa(e.etapa, e.clase)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        <div className="legend" style={{ marginTop: 10 }}>
          <span><span className="dot" style={{ background: "#fbbf24" }} />Estancado (indagación)</span>
          <span><span className="dot" style={{ background: "#38bdf8" }} />Judicializado (investigación / juicio)</span>
          <span><span className="dot" style={{ background: "#22c55e" }} />Resuelto (ejecución de penas)</span>
          <span><span className="dot" style={{ background: "#475569" }} />Sin información</span>
        </div>
      </div>

      {topDeptos.length > 0 && (
        <div className="card">
          <h3><Icon name="map" /> Departamentos por tasa de judicialización</h3>
          <p className="card-sub">
            Tasa = judicializados / procesos de etapa conocida (solo departamentos con ≥ 5.000 procesos, para
            que la tasa sea estable).
          </p>
          <ResponsiveContainer width="100%" height={Math.max(220, topDeptos.length * 30)}>
            <BarChart data={topDeptos} layout="vertical" margin={{ left: 8, right: 24 }}>
              <XAxis type="number" stroke="#94a3b8" fontSize={11} tickFormatter={(v) => `${v}%`} />
              <YAxis type="category" dataKey="name" width={150} stroke="#94a3b8" fontSize={11} />
              <RTooltip cursor={{ fill: "rgba(56,189,248,0.08)" }} content={<ChartTooltip suffix="%" />} />
              <Bar dataKey="tasa" name="Tasa" fill="#38bdf8" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card">
        <h3><Icon name="award" /> Municipios por procesos y tasa de judicialización</h3>
        <p className="card-sub">
          {loading ? "Cargando…" : `${nfmt(municipios.length)} municipios · ordenados por volumen de procesos.`}
        </p>
        <div className="table-filter">
          <input
            value={filtro}
            aria-label="Filtrar por departamento o municipio"
            placeholder="Filtrar por departamento o municipio…"
            onChange={(e) => setFiltro(e.target.value)}
          />
          {!loading && municipios.length > 0 && (
            <ExportButton
              filename="vigia_justicia_municipios.csv"
              cols={[
                { key: "cod_municipio", label: "Cod DANE" },
                { key: "municipio", label: "Municipio" },
                { key: "departamento", label: "Departamento" },
                { key: "total_procesos", label: "Procesos" },
                { key: "n_judicializados", label: "Judicializados" },
                { key: "tasa_judicializacion_pct", label: "Tasa %" },
              ]}
              rows={async () => vista.map((m) => ({
                cod_municipio: m.cod_municipio,
                municipio: m.municipio,
                departamento: m.departamento,
                total_procesos: m.total_procesos,
                n_judicializados: m.n_judicializados,
                tasa_judicializacion_pct: m.tasa_judicializacion_pct.toFixed(2),
              }))}
            />
          )}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="rank">#</th>
                <th className="sortable" onClick={() => toggleSort("municipio")} aria-sort={ariaSort(sortKey === "municipio", sortDir)}>
                  <span className={sortKey === "municipio" ? "active" : ""}>Municipio{arrow("municipio")}</span>
                </th>
                <th className="sortable" onClick={() => toggleSort("departamento")} aria-sort={ariaSort(sortKey === "departamento", sortDir)}>
                  <span className={sortKey === "departamento" ? "active" : ""}>Departamento{arrow("departamento")}</span>
                </th>
                <th className="sortable text-right" onClick={() => toggleSort("total_procesos")} aria-sort={ariaSort(sortKey === "total_procesos", sortDir)}>
                  <span className={sortKey === "total_procesos" ? "active" : ""}>Procesos{arrow("total_procesos")}</span>
                </th>
                <th className="sortable text-right" onClick={() => toggleSort("n_judicializados")} aria-sort={ariaSort(sortKey === "n_judicializados", sortDir)}>
                  <span className={sortKey === "n_judicializados" ? "active" : ""}>Judicializados{arrow("n_judicializados")}</span>
                </th>
                <th className="sortable text-right" onClick={() => toggleSort("tasa_judicializacion_pct")} aria-sort={ariaSort(sortKey === "tasa_judicializacion_pct", sortDir)}>
                  <span className={sortKey === "tasa_judicializacion_pct" ? "active" : ""}>Tasa{arrow("tasa_judicializacion_pct")}</span>
                </th>
              </tr>
            </thead>
            {loading ? <SkeletonRows rows={10} cols={6} /> : (
              <tbody>
                {pg.pageItems.map((m, i) => (
                  <tr key={m.cod_municipio}>
                    <td className="rank">{pg.from + i}</td>
                    <td>{m.municipio}</td>
                    <td className="muted">{m.departamento}</td>
                    <td className="num text-right">{nfmt(m.total_procesos)}</td>
                    <td className="num text-right">{nfmt(m.n_judicializados)}</td>
                    <td className="num text-right">{pct(m.tasa_judicializacion_pct)}</td>
                  </tr>
                ))}
              </tbody>
            )}
          </table>
        </div>
        {!loading && vista.length === 0 && (
          <div className="table-empty">Sin municipios que coincidan con el filtro.</div>
        )}
        {!loading && (
          <Pagination
            page={pg.page} totalPages={pg.totalPages} total={pg.total}
            from={pg.from} to={pg.to} pageSize={pg.pageSize}
            onPage={pg.setPage} onSize={pg.setPageSize}
          />
        )}
      </div>
    </>
  );
}
