import { useEffect, useMemo, useState } from "react";
import { getMunicipios, getBrief, errorMessage, type MunicipioRef, type BriefResponse } from "../api";
import { Combobox, LiveRegion, prettyCat, nfmt, dfmt, type ComboItem } from "./ui";
import { Icon } from "./icons";

// Vista "Informe": genera un informe ejecutivo de seguridad por municipio (IA generativa
// anclada a las cifras oficiales). Reutiliza el selector de municipio y el deep-link del
// drill-down del Panorama (initialCod), igual que el Pronóstico. Endpoint protegido con JWT.
export default function Informe({ initialCod }: { initialCod?: string | null }) {
  const [municipios, setMunicipios] = useState<MunicipioRef[]>([]);
  const [cod, setCod] = useState(initialCod ?? "11001");
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anuncio, setAnuncio] = useState("");      // mensaje para el lector de pantalla
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    getMunicipios()
      .then((ms) => {
        setMunicipios(ms);
        setCod((c) => (ms.some((m) => m.cod_municipio === c) ? c : ms[0]?.cod_municipio ?? c));
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  // Deep-link desde el drill-down del Panorama: al llegar un municipio preseleccionado, úsalo.
  useEffect(() => {
    if (initialCod) setCod(initialCod);
  }, [initialCod]);

  const municipioItems: ComboItem[] = useMemo(
    () => municipios.map((m) => ({ value: m.cod_municipio, label: m.municipio, sub: m.departamento })),
    [municipios],
  );

  const generar = async () => {
    setLoading(true);
    setError(null);
    setBrief(null);
    setCopiado(false);
    setAnuncio("Generando el informe, puede tardar uno o dos minutos.");
    try {
      const r = await getBrief(cod);
      setBrief(r);
      setAnuncio(`Informe generado para ${r.municipio}.`);
    } catch (e: any) {
      const status = e?.response?.status;
      const msg =
        status === 404
          ? "No hay datos suficientes para ese municipio."
          : errorMessage(e);
      setError(msg);
      setAnuncio(`Informe no disponible: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const copiar = async () => {
    if (!brief) return;
    try {
      await navigator.clipboard.writeText(brief.informe);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* el portapapeles puede no estar disponible; ignorar */
    }
  };

  return (
    <>
      <h2 className="section-title">Informe de seguridad municipal</h2>
      <p className="section-sub">
        Informe ejecutivo generado con IA, <b>anclado a las cifras oficiales</b> del municipio
        (panorama, alertas, pronóstico y judicialización).
      </p>
      <LiveRegion message={anuncio} />

      <div className="card">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field">
            Municipio
            <Combobox items={municipioItems} value={cod} onChange={setCod} placeholder="Buscar municipio…" ariaLabel="Municipio" />
          </label>
          <button className="primary" onClick={generar} disabled={loading} style={{ height: 40 }}>
            {loading ? "Generando…" : <><Icon name="file-text" size={16} /> Generar informe</>}
          </button>
        </div>

        {error && (
          <p className="muted" role="alert" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="info" size={15} /> No disponible: {error}
          </p>
        )}

        {!brief && !error && !loading && (
          <div className="empty-state">
            <span className="empty-ic"><Icon name="file-text" size={28} /></span>
            Elija un municipio y pulse <b>Generar informe</b>.
            <div className="muted" style={{ marginTop: 6 }}>
              El texto lo redacta un modelo de lenguaje a partir de las cifras oficiales; según el
              proveedor tarda unos segundos (gestionado) o ~30-90 s con el modelo local en CPU
              (hasta ~2 min en frío).
            </div>
          </div>
        )}

        {loading && (
          <div className="empty-state">
            <span className="typing"><span /><span /><span /></span>
            <div className="muted" style={{ marginTop: 8 }}>Generando el informe…</div>
          </div>
        )}

        {brief && (
          <>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <p className="card-sub" style={{ marginTop: 4 }}>
                {brief.municipio} ({brief.departamento}) · generado {brief.generado}
              </p>
              <button className="ghost" onClick={copiar}>
                <Icon name="download" size={14} /> {copiado ? "Copiado" : "Copiar"}
              </button>
            </div>

            <div
              style={{
                whiteSpace: "pre-wrap",
                lineHeight: 1.6,
                padding: "14px 16px",
                marginTop: 8,
                background: "rgba(148,163,184,0.06)",
                border: "1px solid #26324a",
                borderRadius: 10,
              }}
            >
              {brief.informe}
            </div>

            {/* Cifras que sustentan el informe (auditable, ancladas a los datos). */}
            <div className="sources" style={{ marginTop: 12 }}>
              <span className="chip">
                <Icon name="bar-chart" size={12} /> {nfmt(brief.datos.panorama.total_delitos)} delitos · {brief.datos.panorama.periodo}
              </span>
              {brief.datos.panorama.top_delitos.slice(0, 3).map((d) => (
                <span className="chip" key={d.categoria}>
                  <Icon name="database" size={12} /> {prettyCat(d.categoria)}: {nfmt(d.total)}
                </span>
              ))}
              {brief.datos.justicia && (
                <span className="chip">
                  <Icon name="layers" size={12} /> Judicialización {dfmt(brief.datos.justicia.tasa_judicializacion_pct, 2)} %
                </span>
              )}
            </div>

            <p className="muted" style={{ fontSize: "0.78rem", marginTop: 10 }}>
              Texto generado por IA a partir de datos abiertos oficiales; las cifras reflejan hechos
              registrados, no la criminalidad real. Apoya decisiones agregadas, no la vigilancia de personas.
            </p>
          </>
        )}
      </div>
    </>
  );
}
