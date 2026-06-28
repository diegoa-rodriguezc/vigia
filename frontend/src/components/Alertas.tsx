import { useEffect, useState } from "react";
import { getAnomalies, getStats, type Anomalia, type Stats } from "../api";
import { StatTile, SkeletonRows, Pagination, LiveRegion, ExportButton, nfmt, prettyCat } from "./ui";
import { Icon } from "./icons";

type SortKey = "periodo" | "departamento" | "municipio" | "categoria" | "cantidad" | "score_z" | "severidad";

export default function Alertas() {
  const [data, setData] = useState<Anomalia[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [anuncio, setAnuncio] = useState("");  // mensaje para el lector de pantalla

  const [sev, setSev] = useState<"TODAS" | "ALTA" | "MEDIA">("TODAS");
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");               // texto con debounce
  const [sortKey, setSortKey] = useState<SortKey>("periodo");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  useEffect(() => { getStats().then(setStats).catch(() => {}); }, []);

  // Debounce del buscador: aplica el texto 350 ms después de teclear y vuelve a pág. 1.
  useEffect(() => {
    const t = setTimeout(() => { setQ(qInput); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [qInput]);

  // Carga la página actual desde el servidor (filtro + orden + paginación en BD).
  useEffect(() => {
    let alive = true;
    setLoading(true);
    getAnomalies({
      limit: pageSize,
      offset: (page - 1) * pageSize,
      severidad: sev === "TODAS" ? undefined : sev,
      q: q || undefined,
      sort: sortKey,
      dir: sortDir,
    })
      .then((res) => {
        if (!alive) return;
        setData(res.items); setTotal(res.total); setError(null);
        const filtro = q ? ` para "${q}"` : "";
        setAnuncio(`${nfmt(res.total)} alertas${filtro}.`);
      })
      .catch((e) => {
        if (!alive) return;
        const msg = e?.response?.data?.error ?? e.message;
        setError(msg); setData([]); setTotal(0);
        setAnuncio(`Error al cargar alertas: ${msg}`);
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [page, pageSize, sev, q, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    setPage(1);
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "municipio" || key === "departamento" || key === "categoria" ? "asc" : "desc"); }
  };
  const arrow = (key: SortKey) =>
    sortKey === key ? <span className="arrow"> {sortDir === "asc" ? "▲" : "▼"}</span> : null;

  const th = (key: SortKey, label: string, extra = "") => (
    <th className={`sortable ${extra}`} onClick={() => toggleSort(key)}
        aria-sort={sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : undefined}>
      <span className={sortKey === key ? "active" : ""}>{label}{arrow(key)}</span>
    </th>
  );

  const setSevReset = (f: "TODAS" | "ALTA" | "MEDIA") => { setSev(f); setPage(1); };

  // Export CSV: el endpoint topa el limit a 200, así que se traen TODAS las alertas que
  // coinciden con el filtro actual paginando en lotes (sin truncar en silencio).
  const exportAll = async () => {
    const BATCH = 200;
    const out: Record<string, unknown>[] = [];
    let offset = 0;
    for (let i = 0; i < 200; i++) {  // tope de seguridad: 40.000 filas
      const res = await getAnomalies({
        limit: BATCH, offset,
        severidad: sev === "TODAS" ? undefined : sev,
        q: q || undefined, sort: sortKey, dir: sortDir,
      });
      out.push(...res.items.map((a) => ({
        periodo: a.periodo,
        departamento: a.departamento,
        municipio: a.municipio,
        categoria: prettyCat(a.categoria),
        cantidad: a.cantidad,
        score_z: a.score_z.toFixed(1),
        severidad: a.severidad,
      })));
      offset += res.items.length;
      if (res.items.length < BATCH || offset >= res.total) break;
    }
    return out;
  };

  if (error) return (
    <div className="empty-state" role="alert">
      <span className="empty-ic"><Icon name="inbox" size={28} /></span>
      No hay alertas todavía: {error}
    </div>
  );

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <>
      <h2 className="section-title">Alertas tempranas</h2>
      <p className="section-sub">Meses-municipio con incidencia inusualmente alta (consenso de z-score robusto + IsolationForest).</p>
      <p className="section-sub" style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
        <Icon name="info" size={13} />
        <span>
          Las anomalías son <b>relativas a la propia historia de cada municipio</b> (no señalan los territorios
          "más peligrosos") y reflejan <b>hechos registrados</b>, que pueden seguir el despliegue policial.
          Son un insumo de <b>prevención agregada</b>: no deben usarse para estigmatizar territorios ni para
          vigilar personas.
        </span>
      </p>
      <LiveRegion message={anuncio} />

      <div className="kpis">
        <StatTile icon={<Icon name="bell" />} label="Alertas detectadas" value={nfmt(stats?.anomalias ?? 0)} loading={!stats} hint="total histórico" />
        <StatTile icon={<Icon name="alert-triangle" />} tone="danger" label="Severidad alta" value={nfmt(stats?.anomalias_alta ?? 0)} loading={!stats} hint="picos extremos (z > 5)" />
        <StatTile icon={<Icon name="alert-triangle" />} tone="warn" label="Severidad media" value={nfmt(stats?.anomalias_media ?? 0)} loading={!stats} hint="picos moderados" />
      </div>

      <div className="card">
        <h3><Icon name="bell" /> Alertas</h3>
        <p className="card-sub">
          {loading ? "Cargando…" : `${nfmt(total)} alerta(s) según el filtro · ordenadas en el servidor.`}
        </p>
        <p className="card-sub" style={{ marginTop: -4, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="info" size={13} /> <span><b>z</b> = nº de desviaciones respecto a lo normal de ese municipio y delito; <b>z&nbsp;&gt;&nbsp;5</b> indica un pico extremo (severidad alta).</span>
        </p>

        <div className="table-filter">
          <input
            value={qInput}
            aria-label="Filtrar alertas por departamento, municipio o delito"
            placeholder="Filtrar por departamento, municipio o delito…"
            onChange={(e) => setQInput(e.target.value)}
          />
          {(["TODAS", "ALTA", "MEDIA"] as const).map((f) => (
            <button key={f} className={sev === f ? "primary" : "ghost"} onClick={() => setSevReset(f)}>
              {f === "TODAS" ? "Todas" : f === "ALTA" ? "Alta" : "Media"}
            </button>
          ))}
          {!loading && total > 0 && (
            <ExportButton
              filename="vigia_alertas.csv"
              cols={[
                { key: "periodo", label: "Periodo" },
                { key: "departamento", label: "Departamento" },
                { key: "municipio", label: "Municipio" },
                { key: "categoria", label: "Categoría" },
                { key: "cantidad", label: "Hechos" },
                { key: "score_z", label: "z" },
                { key: "severidad", label: "Severidad" },
              ]}
              rows={exportAll}
            />
          )}
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {th("periodo", "Periodo")}
                {th("departamento", "Departamento")}
                {th("municipio", "Municipio")}
                {th("categoria", "Categoría")}
                {th("cantidad", "Hechos", "text-right")}
                {th("score_z", "z", "text-right")}
                {th("severidad", "Severidad", "text-center")}
              </tr>
            </thead>
            {loading ? <SkeletonRows rows={pageSize} cols={7} /> : (
              <tbody>
                {data.map((a) => (
                  <tr key={`${a.cod_municipio}-${a.categoria}-${a.periodo}`}>
                    <td className="num">{a.periodo}</td>
                    <td className="muted">{a.departamento}</td>
                    <td>{a.municipio}</td>
                    <td>{prettyCat(a.categoria)}</td>
                    <td className="num text-right">{nfmt(a.cantidad)}</td>
                    <td className="num text-right">{a.score_z.toFixed(1)}</td>
                    <td className="text-center"><span className={`badge ${a.severidad}`}>{a.severidad}</span></td>
                  </tr>
                ))}
              </tbody>
            )}
          </table>
        </div>
        {!loading && total === 0 && (
          <div className="table-empty">Sin alertas que coincidan con los filtros.</div>
        )}
        {!loading && (
          <Pagination
            page={page} totalPages={totalPages} total={total}
            from={from} to={to} pageSize={pageSize}
            onPage={setPage} onSize={(s) => { setPageSize(s); setPage(1); }}
          />
        )}
      </div>
    </>
  );
}
