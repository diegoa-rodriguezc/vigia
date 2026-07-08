import { useEffect, useMemo, useState } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { getMunicipios, getCategories, getTimeSeries, getForecast, type MunicipioRef } from "../api";
import { Combobox, ChartTooltip, LiveRegion, ExportButton, prettyCat, type ComboItem } from "./ui";
import { Icon } from "./icons";

interface Punto { periodo: string; historico?: number; pronostico?: number; banda?: [number, number]; }

export default function Forecast({ initialCod }: { initialCod?: string | null }) {
  const [municipios, setMunicipios] = useState<MunicipioRef[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [cod, setCod] = useState(initialCod ?? "11001");
  const [categoria, setCategoria] = useState("HOMICIDIO");
  const [serie, setSerie] = useState<Punto[]>([]);
  const [splitIdx, setSplitIdx] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ran, setRan] = useState(false);
  const [anuncio, setAnuncio] = useState("");  // mensaje para el lector de pantalla

  useEffect(() => {
    getMunicipios()
      .then((ms) => {
        setMunicipios(ms);
        // Conserva el municipio actual si existe; si no (p. ej. otro dataset), usa el primero.
        setCod((c) => (ms.some((m) => m.cod_municipio === c) ? c : ms[0]?.cod_municipio ?? c));
      })
      .catch(() => {});
  }, []);

  // Deep-link desde el drill-down del Panorama: al llegar un municipio preseleccionado, úsalo.
  useEffect(() => {
    if (initialCod) setCod(initialCod);
  }, [initialCod]);

  // Las categorías dependen del municipio: solo se ofrecen las que TIENEN historial allí
  // (así no se puede elegir una combinación sin datos). Si la categoría seleccionada deja
  // de estar disponible al cambiar de municipio, se cambia a la primera de la lista.
  useEffect(() => {
    if (!cod) return;
    getCategories(cod)
      .then((cs) => { setCategorias(cs); setCategoria((cat) => (cs.includes(cat) ? cat : cs[0] ?? "")); })
      .catch(() => {});
  }, [cod]);

  const municipioItems: ComboItem[] = useMemo(
    () => municipios.map((m) => ({ value: m.cod_municipio, label: m.municipio, sub: m.departamento })),
    [municipios],
  );

  const run = async () => {
    setLoading(true);
    setError(null);
    setAnuncio("Calculando el pronóstico…");
    try {
      const [hist, fc] = await Promise.all([
        getTimeSeries(cod, categoria),
        getForecast(cod, categoria, 6),
      ]);
      const tail = hist.slice(-24);
      const merged: Punto[] = tail.map((p) => ({ periodo: p.periodo, historico: p.cantidad }));
      // Punto de empalme: el último histórico también ancla la línea de pronóstico.
      if (tail.length && fc.pronostico.length) {
        merged[merged.length - 1].pronostico = tail[tail.length - 1].cantidad;
      }
      setSplitIdx(merged.length - 1);
      fc.pronostico.forEach((p) => merged.push({
        periodo: p.periodo,
        pronostico: p.prediccion,
        // Banda de incertidumbre (~80%) cuando el modelo la provee.
        banda: p.limite_inferior != null && p.limite_superior != null
          ? [p.limite_inferior, p.limite_superior]
          : undefined,
      }));
      setSerie(merged);
      setRan(true);
      const muni = municipios.find((m) => m.cod_municipio === cod)?.municipio ?? cod;
      setAnuncio(`Pronóstico listo para ${prettyCat(categoria)} en ${muni}.`);
    } catch (e: any) {
      const muni = municipios.find((m) => m.cod_municipio === cod)?.municipio ?? cod;
      let msg: string;
      if (e?.response?.status === 404) {
        msg = `No hay historial de ${prettyCat(categoria)} en ${muni} para pronosticar.`;
      } else {
        msg = e?.response?.data?.detail ?? e?.response?.data?.error ?? e.message;
      }
      setError(msg);
      setAnuncio(`Pronóstico no disponible: ${msg}`);
      setSerie([]);
    } finally {
      setLoading(false);
    }
  };

  const selected = municipios.find((m) => m.cod_municipio === cod);

  return (
    <>
      <h2 className="section-title">Pronóstico de criminalidad</h2>
      <p className="section-sub">Proyección a 6 meses con un modelo global de gradient boosting, validado por backtesting temporal.</p>
      <LiveRegion message={anuncio} />


      <div className="card">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field">
            Municipio
            <Combobox items={municipioItems} value={cod} onChange={setCod} placeholder="Buscar municipio…" ariaLabel="Municipio" />
          </label>
          <label className="field">
            Tipo de delito
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              {categorias.map((c) => <option key={c} value={c}>{prettyCat(c)}</option>)}
            </select>
          </label>
          <button className="primary" onClick={run} disabled={loading} style={{ height: 40 }}>
            {loading ? "Calculando…" : <><Icon name="trending-up" size={16} /> Pronosticar</>}
          </button>
        </div>

        {error && (
          <p className="muted" role="alert" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="info" size={15} /> No disponible: {error}
          </p>
        )}

        {!ran && !error && (
          <div className="empty-state">
            <span className="empty-ic"><Icon name="sparkles" size={28} /></span>
            Elige un municipio y un tipo de delito, luego pulsa <b>Pronosticar</b>.
            <div className="muted" style={{ marginTop: 6 }}>El modelo se entrena por código y categoría, sin sesgo por nombre.</div>
          </div>
        )}

        {serie.length > 0 && (
          <>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <p className="card-sub" style={{ marginTop: 4 }}>
                {selected ? `${selected.municipio} (${selected.departamento})` : cod} · {prettyCat(categoria)} ·
                últimos 24 meses + 6 de pronóstico
              </p>
              <ExportButton
                filename={`vigia_pronostico_${cod}_${categoria}.csv`}
                cols={[
                  { key: "periodo", label: "Periodo" },
                  { key: "historico", label: "Histórico" },
                  { key: "pronostico", label: "Pronóstico" },
                  { key: "limite_inferior", label: "Límite inferior" },
                  { key: "limite_superior", label: "Límite superior" },
                ]}
                rows={serie.map((p) => ({
                  periodo: p.periodo,
                  historico: p.historico ?? "",
                  pronostico: p.pronostico ?? "",
                  limite_inferior: p.banda?.[0] ?? "",
                  limite_superior: p.banda?.[1] ?? "",
                }))}
              />
            </div>
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={serie} margin={{ top: 24, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#26324a" />
                <XAxis dataKey="periodo" stroke="#94a3b8" fontSize={11} minTickGap={24} />
                <YAxis stroke="#94a3b8" fontSize={11} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                {splitIdx != null && serie[splitIdx] && (
                  <ReferenceLine x={serie[splitIdx].periodo} stroke="#475569" strokeDasharray="4 4" label={{ value: "hoy", fill: "#64748b", fontSize: 11, position: "top" }} />
                )}
                {/* Banda de incertidumbre (~80%) del pronóstico, sombreada bajo la línea. */}
                <Area type="monotone" dataKey="banda" name="Incertidumbre ~80%" stroke="none" fill="#fbbf24" fillOpacity={0.15} connectNulls />
                <Line type="monotone" dataKey="historico" name="Histórico" stroke="#38bdf8" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="pronostico" name="Pronóstico" stroke="#fbbf24" strokeWidth={2} strokeDasharray="6 4" dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="muted" style={{ marginTop: 6, fontSize: "0.8rem" }}>
              Límite declarado: en delitos de gran volumen con caída sostenida (p. ej. el homicidio en las
              grandes ciudades) el pronóstico puede quedar por encima del nivel de los últimos meses; el
              detalle, con sus cifras, está en la metodología (CRISP-ML(Q), «Dónde cede»).
            </p>
          </>
        )}
      </div>
    </>
  );
}
