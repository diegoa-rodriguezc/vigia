import { useEffect, useMemo, useState } from "react";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getMunicipios, getCategories, getSimulate, type MunicipioRef, type SimulateResponse } from "../api";
import { Combobox, ChartTooltip, LiveRegion, ExportButton, prettyCat, type ComboItem } from "./ui";
import { Icon } from "./icons";

export default function Simulador() {
  const [municipios, setMunicipios] = useState<MunicipioRef[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [cod, setCod] = useState("11001");
  const [categoria, setCategoria] = useState("HOMICIDIO");
  // Palancas del escenario. Por defecto, una intervención que se espera reduzca 15% con
  // despliegue gradual de 3 meses (valores ilustrativos, editables).
  const [intervencion, setIntervencion] = useState(-15);
  const [ramp, setRamp] = useState(3);
  const [shockPob, setShockPob] = useState(0);
  const [res, setRes] = useState<SimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [anuncio, setAnuncio] = useState("");

  useEffect(() => {
    getMunicipios()
      .then((ms) => {
        setMunicipios(ms);
        setCod((c) => (ms.some((m) => m.cod_municipio === c) ? c : ms[0]?.cod_municipio ?? c));
      })
      .catch(() => {});
  }, []);

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
    setAnuncio("Simulando el escenario…");
    try {
      const r = await getSimulate({
        cod_municipio: cod, categoria, horizon: 6,
        intervencion_pct: intervencion, ramp_meses: ramp, shock_poblacion_pct: shockPob,
      });
      setRes(r);
      const muni = municipios.find((m) => m.cod_municipio === cod)?.municipio ?? cod;
      setAnuncio(`Escenario listo para ${prettyCat(categoria)} en ${muni}: ${r.evitados_total} hechos evitados acumulados.`);
    } catch (e: any) {
      let msg: string;
      const muni = municipios.find((m) => m.cod_municipio === cod)?.municipio ?? cod;
      if (e?.response?.status === 404) msg = `No hay historial de ${prettyCat(categoria)} en ${muni} para simular.`;
      else msg = e?.response?.data?.detail ?? e?.response?.data?.error ?? e.message;
      setError(msg);
      setAnuncio(`Simulación no disponible: ${msg}`);
      setRes(null);
    } finally {
      setLoading(false);
    }
  };

  // Datos del gráfico: base vs escenario por mes + hechos evitados (barras secundarias).
  const chart = res?.delta ?? [];
  const evitadosLabel = res && res.evitados_total >= 0 ? "evitados" : "adicionales";

  return (
    <>
      <h2 className="section-title">Simulación de escenarios "¿y si…?"</h2>
      <p className="section-sub">
        Proyecta el efecto de una intervención y/o un cambio de población sobre el pronóstico base,
        y estima los hechos evitados. Apoya la decisión preventiva; no es una certeza.
      </p>
      <LiveRegion message={anuncio} />

      <div className="card">
        <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
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
          <label className="field">
            Efecto de la intervención: <b>{intervencion}%</b>
            <input type="range" min={-50} max={20} step={5} value={intervencion}
              onChange={(e) => setIntervencion(Number(e.target.value))} aria-label="Efecto esperado de la intervención en porcentaje" />
          </label>
          <label className="field">
            Despliegue (meses): <b>{ramp}</b>
            <input type="range" min={0} max={12} step={1} value={ramp}
              onChange={(e) => setRamp(Number(e.target.value))} aria-label="Meses hasta el efecto pleno de la intervención" />
          </label>
          <label className="field">
            Cambio de población: <b>{shockPob}%</b>
            <input type="range" min={-20} max={20} step={5} value={shockPob}
              onChange={(e) => setShockPob(Number(e.target.value))} aria-label="Cambio de población en porcentaje" />
          </label>
          <button className="primary" onClick={run} disabled={loading} style={{ height: 40 }}>
            {loading ? "Simulando…" : <><Icon name="sliders" size={16} /> Simular</>}
          </button>
        </div>

        {error && (
          <p className="muted" role="alert" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="info" size={15} /> No disponible: {error}
          </p>
        )}

        {!res && !error && (
          <div className="empty-state">
            <span className="empty-ic"><Icon name="sliders" size={28} /></span>
            Ajusta las palancas y pulsa <b>Simular</b> para comparar el escenario con el pronóstico base.
            <div className="muted" style={{ marginTop: 6 }}>
              La población es una palanca del modelo; la intervención es un supuesto del usuario.
            </div>
          </div>
        )}

        {res && chart.length > 0 && (
          <>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div className="kpi-inline">
                <span className="kpi-big">{Math.abs(res.evitados_total).toLocaleString("es-CO")}</span>
                <span className="muted"> hechos {evitadosLabel} acumulados en 6 meses</span>
              </div>
              <ExportButton
                filename={`vigia_simulacion_${cod}_${categoria}.csv`}
                cols={[
                  { key: "periodo", label: "Periodo" },
                  { key: "base", label: "Pronóstico base" },
                  { key: "escenario", label: "Escenario" },
                  { key: "evitados", label: "Evitados (mes)" },
                  { key: "evitados_acumulado", label: "Evitados (acum.)" },
                ]}
                rows={chart.map((d) => ({
                  periodo: d.periodo, base: d.base, escenario: d.escenario,
                  evitados: d.evitados, evitados_acumulado: d.evitados_acumulado,
                }))}
              />
            </div>
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={chart} margin={{ top: 24, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#26324a" />
                <XAxis dataKey="periodo" stroke="#94a3b8" fontSize={11} minTickGap={24} />
                <YAxis stroke="#94a3b8" fontSize={11} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                <Bar dataKey="evitados" name={`Hechos ${evitadosLabel} (mes)`} fill="#34d399" fillOpacity={0.35} />
                <Line type="monotone" dataKey="base" name="Pronóstico base" stroke="#fbbf24" strokeWidth={2} strokeDasharray="6 4" dot={false} />
                <Line type="monotone" dataKey="escenario" name="Con intervención" stroke="#38bdf8" strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="muted" style={{ marginTop: 8, display: "inline-flex", alignItems: "flex-start", gap: 6 }}>
              <Icon name="info" size={15} /> {res.nota}
            </p>
          </>
        )}
      </div>
    </>
  );
}
