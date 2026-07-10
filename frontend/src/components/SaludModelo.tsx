import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getMonitoring, errorMessage, type ModelHealth, type Estado } from "../api";
import { ChartTooltip, nfmt, dfmt } from "./ui";
import { Icon } from "./icons";

const LABEL: Record<Estado, string> = { verde: "Saludable", amarillo: "Atención", rojo: "Crítico" };

// El estado (verde/amarillo/rojo) va SOLO en el color, así que el punto lleva etiqueta accesible
// por defecto; `decorativo` lo oculta al lector de pantalla cuando el texto adyacente ya nombra el
// estado (evita que lo anuncie dos veces).
function Semaforo({ estado, size = 12, decorativo = false }: { estado: Estado; size?: number; decorativo?: boolean }) {
  const props = { className: `sem-dot sem-${estado}`, style: { width: size, height: size } };
  return decorativo
    ? <span {...props} aria-hidden="true" />
    : <span {...props} role="img" aria-label={`Estado: ${LABEL[estado]}`} />;
}

export default function SaludModelo() {
  const [data, setData] = useState<ModelHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMonitoring()
      .then(setData)
      .catch((e) => setError(e?.response?.status === 404
        ? "Aún no hay un reporte de salud del modelo disponible."
        : errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="skeleton" style={{ height: 320 }} />;
  if (error) return (
    <div className="empty-state">
      <span className="empty-ic"><Icon name="activity" size={28} /></span>
      {error}
    </div>
  );
  if (!data) return null;

  const { frescura: fr, deriva_datos: dr, backtest_extendido: bt, estado_global } = data;
  const chart = (bt?.por_paso ?? []).map((p) => ({
    paso: p.paso, modelo: p.mae, persistencia: p.baseline_mae,
  }));

  return (
    <>
      <h2 className="section-title">Salud del modelo</h2>
      <p className="section-sub">
        Monitoreo continuo (sin reentrenar): frescura de datos, deriva de distribución y validación
        del horizonte largo. Refuerza la trazabilidad y el gobierno del modelo.
      </p>

      <div className="card" style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <Semaforo estado={estado_global} size={16} decorativo />
        <strong>Estado global: {LABEL[estado_global]}</strong>
        <span className="muted" style={{ fontSize: "0.8rem" }}>· generado {data.generado_en}</span>
      </div>

      <div className="kpis">
        <div className="kpi">
          <div className="kpi-top">
            <span className="kpi-label">Frescura de datos</span>
            <Semaforo estado={fr.estado} />
          </div>
          <div className="kpi-value">{fr.lag_meses ?? "—"} <span style={{ fontSize: "0.9rem" }}>{fr.lag_meses === 1 ? "mes" : "meses"}</span></div>
          <div className="kpi-hint">de rezago · datos a {fr.periodo_max ?? "—"}</div>
        </div>

        <div className="kpi">
          <div className="kpi-top">
            <span className="kpi-label">Deriva de datos (PSI)</span>
            <Semaforo estado={dr.estado} />
          </div>
          <div className="kpi-value">{dfmt(dr.psi, 3)}</div>
          <div className="kpi-hint">
            {dr.nota ?? `cambio de volumen ${dr.cambio_volumen_pct != null ? dfmt(dr.cambio_volumen_pct, 1) : "—"} % (últimos ${dr.ventana_meses} m)`}
          </div>
        </div>

        {bt && (
          <div className="kpi">
            <div className="kpi-top">
              <span className="kpi-label">Backtest a {bt.horizon} meses</span>
              <Semaforo estado={bt.estado} />
            </div>
            <div className="kpi-value">{dfmt(bt.mae, 2)}</div>
            <div className="kpi-hint">
              MAE vs {dfmt(bt.baseline_mae, 2)} persistencia ·{" "}
              {bt.supera_baseline_mae ? "supera la línea base" : "no la supera"}
            </div>
          </div>
        )}
      </div>

      {chart.length > 0 && (
        <div className="card">
          <h3><Icon name="trending-up" /> Degradación del error por horizonte</h3>
          <p className="card-sub">
            Error (MAE) del modelo vs la persistencia ingenua a cada mes de pronóstico, con el mismo
            backtest walk-forward sin fuga. El error crece con el horizonte (recursión).
          </p>
          <div role="img" aria-label="Gráfica de líneas del error (MAE) del modelo frente a la persistencia ingenua, por mes de pronóstico.">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chart} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#26324a" />
              <XAxis dataKey="paso" stroke="#94a3b8" fontSize={11} label={{ value: "mes de pronóstico", position: "insideBottom", offset: -2, fill: "#64748b", fontSize: 11 }} />
              <YAxis stroke="#94a3b8" fontSize={11} />
              <Tooltip content={<ChartTooltip />} />
              <Legend />
              <Line type="monotone" dataKey="modelo" name="Modelo (MAE)" stroke="#38bdf8" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="persistencia" name="Persistencia (MAE)" stroke="#fbbf24" strokeWidth={2} strokeDasharray="6 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          </div>
          <p className="muted" style={{ marginTop: 6, fontSize: "0.8rem" }}>
            {bt && `Validado sobre ${bt.n_origins === 1 ? "1 origen temporal" : `${nfmt(bt.n_origins)} orígenes temporales`}.`} PSI: &lt;0,1 estable · 0,1-0,25 deriva moderada · &gt;0,25 significativa.
          </p>
        </div>
      )}
    </>
  );
}
