import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getMonitoring, type ModelHealth, type Estado } from "../api";
import { ChartTooltip, nfmt } from "./ui";
import { Icon } from "./icons";

const LABEL: Record<Estado, string> = { verde: "Saludable", amarillo: "Atención", rojo: "Crítico" };

function Semaforo({ estado, size = 12 }: { estado: Estado; size?: number }) {
  return <span className={`sem-dot sem-${estado}`} style={{ width: size, height: size }} aria-hidden="true" />;
}

export default function SaludModelo() {
  const [data, setData] = useState<ModelHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMonitoring()
      .then(setData)
      .catch((e) => setError(e?.response?.status === 404
        ? "Aún no hay reporte de salud. Ejecuta el pipeline o `vigia health`."
        : (e?.response?.data?.error ?? e.message)))
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
        <Semaforo estado={estado_global} size={16} />
        <strong>Estado global: {LABEL[estado_global]}</strong>
        <span className="muted" style={{ fontSize: "0.8rem" }}>· generado {data.generado_en}</span>
      </div>

      <div className="kpis">
        <div className="kpi">
          <div className="kpi-top">
            <span className="kpi-label">Frescura de datos</span>
            <Semaforo estado={fr.estado} />
          </div>
          <div className="kpi-value">{fr.lag_meses ?? "—"} <span style={{ fontSize: "0.9rem" }}>mes(es)</span></div>
          <div className="kpi-hint">de rezago · datos a {fr.periodo_max ?? "—"}</div>
        </div>

        <div className="kpi">
          <div className="kpi-top">
            <span className="kpi-label">Deriva de datos (PSI)</span>
            <Semaforo estado={dr.estado} />
          </div>
          <div className="kpi-value">{dr.psi.toFixed(3)}</div>
          <div className="kpi-hint">
            {dr.nota ?? `cambio de volumen ${dr.cambio_volumen_pct ?? "—"}% (últimos ${dr.ventana_meses} m)`}
          </div>
        </div>

        {bt && (
          <div className="kpi">
            <div className="kpi-top">
              <span className="kpi-label">Backtest a {bt.horizon} meses</span>
              <Semaforo estado={bt.estado} />
            </div>
            <div className="kpi-value">{bt.mae.toFixed(2)}</div>
            <div className="kpi-hint">
              MAE vs {bt.baseline_mae.toFixed(2)} persistencia ·{" "}
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
          <p className="muted" style={{ marginTop: 6, fontSize: "0.8rem" }}>
            {bt && `Validado sobre ${nfmt(bt.n_origins)} origen(es) temporales.`} PSI: &lt;0,1 estable · 0,1-0,25 deriva moderada · &gt;0,25 significativa.
          </p>
        </div>
      )}
    </>
  );
}
