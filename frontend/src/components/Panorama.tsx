import { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import {
  getSummary, getDepartamentos, getStats,
  type MunicipioResumen, type DepartamentoResumen, type Stats,
} from "../api";
import { StatTile, ChartTooltip, SkeletonRows, Pagination, usePagination, nfmt, ExportButton } from "./ui";
import { Icon } from "./icons";
import ChoroplethMap from "./ChoroplethMap";
import SenalesRecientes from "./SenalesRecientes";
import MunicipioDrilldown from "./MunicipioDrilldown";

type SortKey = "departamento" | "municipio" | "total_delitos" | "categorias";

// `aria-sort` para la cabecera de la columna activa (lectores de pantalla).
const ariaSort = (active: boolean, dir: "asc" | "desc"): "ascending" | "descending" | undefined =>
  active ? (dir === "asc" ? "ascending" : "descending") : undefined;

// Se cargan todos los municipios (≈1.118) y se paginan en cliente; el payload es
// pequeño y permite navegar el ranking nacional completo, no solo el top 50.
const SUMMARY_LIMIT = 2000;

export default function Panorama({
  onVerPronostico,
  onVerInforme,
}: {
  onVerPronostico?: (cod: string) => void;
  onVerInforme?: (cod: string) => void;
}) {
  const [data, setData] = useState<MunicipioResumen[]>([]);
  const [sel, setSel] = useState<MunicipioResumen | null>(null);  // municipio del drill-down
  const [selDepto, setSelDepto] = useState<{ cod: string; nombre: string } | null>(null); // depto para señales de prensa
  const [departamentos, setDepartamentos] = useState<DepartamentoResumen[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [statsErr, setStatsErr] = useState(false);
  const [mapErr, setMapErr] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Estado de la tabla: filtro de texto y orden por columna.
  const [filtro, setFiltro] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("total_delitos");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    getSummary(SUMMARY_LIMIT)
      .then(setData)
      .catch((e) => setError(e?.response?.data?.error ?? e.message))
      .finally(() => setLoading(false));
    getDepartamentos().then(setDepartamentos).catch(() => setMapErr(true));
    // KPIs con totales reales calculados en BD (COUNT/SUM), no derivados del top 20.
    getStats().then(setStats).catch(() => setStatsErr(true));
  }, []);

  // Valor de KPI: muestra "—" si falló la carga de totales (no un 0 engañoso).
  const kpiVal = (v: number | undefined) => (statsErr ? "—" : nfmt(v ?? 0));

  // Ranking nacional estable por incidencia delictiva (no cambia al reordenar/filtrar).
  const rankByHechos = useMemo(() => {
    const m = new Map<string, number>();
    [...data].sort((a, b) => b.total_delitos - a.total_delitos).forEach((d, i) => m.set(d.cod_municipio, i + 1));
    return m;
  }, [data]);

  const vista = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    const filtrada = q
      ? data.filter((d) => d.municipio.toLowerCase().includes(q) || d.departamento.toLowerCase().includes(q))
      : data;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtrada].sort((a, b) => {
      const cmp = (sortKey === "municipio" || sortKey === "departamento")
        ? a[sortKey].localeCompare(b[sortKey], "es")
        : a[sortKey] - b[sortKey];
      return cmp * dir;
    });
  }, [data, filtro, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "municipio" || key === "departamento" ? "asc" : "desc"); }
  };
  const arrow = (key: SortKey) =>
    sortKey === key ? <span className="arrow"> {sortDir === "asc" ? "▲" : "▼"}</span> : null;

  // Paginación en cliente sobre la vista filtrada/ordenada; vuelve a la pág. 1 al filtrar.
  const pg = usePagination(vista, 10, `${filtro}|${sortKey}|${sortDir}`);

  if (error) return (
    <div className="empty-state">
      <span className="empty-ic"><Icon name="inbox" size={28} /></span>
      No hay datos todavía: {error}
      <div className="muted" style={{ marginTop: 8 }}>Ejecuta el pipeline: <code>make docker-pipeline</code></div>
    </div>
  );

  const chartData = data.slice(0, 10).map((d) => ({ name: d.municipio, total: d.total_delitos }));
  const top = data[0];

  return (
    <>
      <h2 className="section-title">Panorama nacional</h2>
      <p className="section-sub">Incidencia delictiva agregada por municipio, sobre datos abiertos oficiales.</p>
      {stats && (
        <p className="muted" style={{ marginTop: -10, marginBottom: 14, fontSize: "0.8rem", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="activity" size={13} /> Datos actualizados a {stats.periodo_max}.
        </p>
      )}

      <div className="kpis">
        <StatTile icon={<Icon name="building" />} label="Municipios monitoreados" value={kpiVal(stats?.municipios)} loading={!stats && !statsErr} hint={stats ? `en ${stats.departamentos} departamentos` : undefined} />
        <StatTile icon={<Icon name="activity" />} tone="danger" label="Delitos registrados" value={kpiVal(stats?.total_delitos)} loading={!stats && !statsErr} hint={stats ? `${stats.periodo_min} a ${stats.periodo_max}` : undefined} />
        <StatTile icon={<Icon name="shield" />} label="Resultados operativos" value={kpiVal(stats?.total_respuestas)} loading={!stats && !statsErr} hint="capturas, incautaciones, recuperaciones" />
        <StatTile icon={<Icon name="layers" />} label="Tipos de delito" value={statsErr ? "—" : (stats?.categorias ?? 0)} loading={!stats && !statsErr} hint="categorías unificadas" />
        <StatTile icon={<Icon name="bell" />} tone="danger" label="Alertas detectadas" value={kpiVal(stats?.anomalias)} loading={!stats && !statsErr} hint={stats ? `${nfmt(stats.anomalias_alta)} alta · ${nfmt(stats.anomalias_media)} media` : undefined} />
        <StatTile icon={<Icon name="map-pin" />} label="Municipio más afectado" value={loading ? "—" : (top?.municipio ?? "—")} loading={loading} hint={top ? `${nfmt(top.total_delitos)} delitos` : undefined} />
      </div>
      {statsErr && (
        <p className="muted" style={{ marginTop: -8, marginBottom: 16, fontSize: "0.82rem", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="alert-triangle" size={14} /> No se pudieron cargar los totales del tablero.
        </p>
      )}

      <div className="panorama-grid">
        <div className="card">
          <h3><Icon name="award" /> Municipios con mayor incidencia</h3>
          <div className="table-filter">
            <input
              value={filtro}
              aria-label="Filtrar por nombre departamento o municipio"
              placeholder="Filtrar por departamento o municipio…"
              onChange={(e) => setFiltro(e.target.value)}
            />
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              {loading ? "" : `${nfmt(vista.length)} de ${nfmt(data.length)}`}
            </span>
            {!loading && (
              <ExportButton
                filename="vigia_municipios.csv"
                cols={[
                  { key: "rank", label: "#" },
                  { key: "departamento", label: "Departamento" },
                  { key: "municipio", label: "Municipio" },
                  { key: "total_delitos", label: "Delitos" },
                  { key: "categorias", label: "Tipos" },
                ]}
                rows={vista.map((m) => ({
                  rank: rankByHechos.get(m.cod_municipio) ?? "",
                  departamento: m.departamento,
                  municipio: m.municipio,
                  total_delitos: m.total_delitos,
                  categorias: m.categorias,
                }))}
              />
            )}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="rank">#</th>
                  <th className="sortable" onClick={() => toggleSort("departamento")} aria-sort={ariaSort(sortKey === "departamento", sortDir)}>
                    <span className={sortKey === "departamento" ? "active" : ""}>Departamento{arrow("departamento")}</span>
                  </th>
                  <th className="sortable" onClick={() => toggleSort("municipio")} aria-sort={ariaSort(sortKey === "municipio", sortDir)}>
                    <span className={sortKey === "municipio" ? "active" : ""}>Municipio{arrow("municipio")}</span>
                  </th>
                  <th className="sortable text-right" onClick={() => toggleSort("total_delitos")} aria-sort={ariaSort(sortKey === "total_delitos", sortDir)}>
                    <span className={sortKey === "total_delitos" ? "active" : ""}>Delitos{arrow("total_delitos")}</span>
                  </th>
                  <th className="sortable text-right" onClick={() => toggleSort("categorias")} aria-sort={ariaSort(sortKey === "categorias", sortDir)}>
                    <span className={sortKey === "categorias" ? "active" : ""}>Tipos{arrow("categorias")}</span>
                  </th>
                </tr>
              </thead>
              {loading ? <SkeletonRows rows={8} cols={5} /> : (
                <tbody>
                  {pg.pageItems.map((m) => (
                    <tr key={m.cod_municipio}>
                      <td className="rank">{rankByHechos.get(m.cod_municipio)}</td>
                      <td className="muted">{m.departamento}</td>
                      <td>
                        <button
                          className="link-btn"
                          onClick={() => setSel(m)}
                          aria-label={`Ver detalle de ${m.municipio}`}
                        >
                          {m.municipio}
                        </button>
                      </td>
                      <td className="num text-right">{nfmt(m.total_delitos)}</td>
                      <td className="num text-right">{m.categorias}</td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
          </div>
          {!loading && vista.length === 0 && (
            <div className="table-empty">Sin municipios que coincidan con "{filtro}".</div>
          )}
          {!loading && (
            <Pagination
              page={pg.page} totalPages={pg.totalPages} total={pg.total}
              from={pg.from} to={pg.to} pageSize={pg.pageSize}
              onPage={pg.setPage} onSize={pg.setPageSize}
            />
          )}
        </div>

        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <h3><Icon name="bar-chart" /> Top 10 por número de delitos</h3>
          {loading ? <div className="skeleton" style={{ flex: 1, minHeight: 360 }} /> : (
            <div style={{ flex: 1, minHeight: 360 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 16 }}>
                  <XAxis type="number" stroke="#94a3b8" fontSize={11} />
                  <YAxis type="category" dataKey="name" width={120} stroke="#94a3b8" fontSize={12} />
                  <RTooltip cursor={{ fill: "rgba(56,189,248,0.08)" }} content={<ChartTooltip />} />
                  <Bar dataKey="total" name="Delitos" fill="#38bdf8" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div style={{ gridColumn: "1 / -1", display: "flex", flexWrap: "wrap", gap: 16, alignItems: "stretch" }}>
          <div className="card" style={{ flex: "3 1 380px", minWidth: 0 }}>
            <h3><Icon name="map" /> Mapa coroplético por departamento</h3>
            <p className="card-sub">
              Intensidad de color según los delitos registrados del departamento (clases por cuantiles).{" "}
              Haz clic en un departamento para ver sus señales de prensa recientes.
            </p>
            {mapErr
              ? <div className="table-empty">No se pudo cargar el mapa por departamento.</div>
              : departamentos.length === 0
                ? <div className="skeleton" style={{ height: 460 }} />
                : <ChoroplethMap
                    departamentos={departamentos}
                    onSelectDepto={(cod, nombre) => setSelDepto({ cod, nombre })}
                    selectedCod={selDepto?.cod}
                  />}
          </div>
          <div style={{ flex: "1 1 260px", minWidth: 0, display: "flex" }}>
            <SenalesRecientes
              cod={selDepto?.cod}
              nombre={selDepto?.nombre}
              onClear={() => setSelDepto(null)}
            />
          </div>
        </div>
      </div>

      {sel && (
        <MunicipioDrilldown
          muni={sel}
          onClose={() => setSel(null)}
          onVerPronostico={onVerPronostico
            ? (cod) => { setSel(null); onVerPronostico(cod); }
            : undefined}
          onVerInforme={onVerInforme
            ? (cod) => { setSel(null); onVerInforme(cod); }
            : undefined}
        />
      )}
    </>
  );
}
