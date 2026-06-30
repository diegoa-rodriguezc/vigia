import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import { getMunicipioDetalle, type CategoriaTotal, type MunicipioResumen } from "../api";
import { ChartTooltip, prettyCat, nfmt, ExportButton } from "./ui";
import { Icon } from "./icons";

interface Props {
  muni: MunicipioResumen;
  onClose: () => void;
  onVerPronostico?: (cod: string) => void;
  onVerInforme?: (cod: string) => void;
}

// Drill-down de un municipio: desglose por categoría de delito + acceso al pronóstico y al
// informe ejecutivo. Modal accesible (role=dialog, aria-modal, Escape, retorno de foco al cerrar).
export default function MunicipioDrilldown({ muni, onClose, onVerPronostico, onVerInforme }: Props) {
  const [detalle, setDetalle] = useState<CategoriaTotal[] | null>(null);
  const [error, setError] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    getMunicipioDetalle(muni.cod_municipio).then(setDetalle).catch(() => setError(true));
  }, [muni.cod_municipio]);

  // Foco inicial al botón de cierre y retorno del foco al elemento que abrió el modal.
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => prev?.focus?.();
  }, []);

  // Cerrar con Escape; trampa de foco básica con Tab dentro del diálogo.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Top categorías de DELITO (el desglose de respuesta institucional se resume aparte).
  const delitos = useMemo(
    () => (detalle ?? []).filter((d) => d.naturaleza === "delito"),
    [detalle],
  );
  const chartData = delitos.slice(0, 8).map((d) => ({ name: prettyCat(d.categoria), total: d.total }));

  return (
    <div className="auth-overlay" onMouseDown={onClose}>
      <div
        className="drilldown-modal card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dd-title"
        ref={dialogRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="auth-head">
          <span className="logo" role="img" aria-label="Municipio"><Icon name="map-pin" size={18} /></span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="dd-title" style={{ margin: 0, fontSize: "1.1rem" }}>{muni.municipio}</h2>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              {muni.departamento} · DANE {muni.cod_municipio}
            </div>
          </div>
          <button ref={closeRef} className="ghost auth-close" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>

        <div className="dd-kpis">
          <div className="dd-kpi"><span className="dd-kpi-v">{nfmt(muni.total_delitos)}</span><span className="muted">delitos</span></div>
          <div className="dd-kpi"><span className="dd-kpi-v">{nfmt(muni.total_respuestas)}</span><span className="muted">resultados operativos</span></div>
          <div className="dd-kpi"><span className="dd-kpi-v">{muni.categorias}</span><span className="muted">tipos de delito</span></div>
        </div>

        <h3 style={{ marginBottom: 4 }}><Icon name="bar-chart" size={16} /> Delitos por categoría</h3>
        {error ? (
          <div className="table-empty">No se pudo cargar el desglose del municipio.</div>
        ) : detalle === null ? (
          <div className="skeleton" style={{ height: 240 }} />
        ) : chartData.length === 0 ? (
          <div className="table-empty">Sin desglose de delitos para este municipio.</div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 34)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" stroke="#94a3b8" fontSize={11} />
              <YAxis type="category" dataKey="name" width={140} stroke="#94a3b8" fontSize={11} />
              <RTooltip cursor={{ fill: "rgba(56,189,248,0.08)" }} content={<ChartTooltip />} />
              <Bar dataKey="total" name="Delitos" fill="#38bdf8" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}

        <div className="dd-actions">
          {detalle && delitos.length > 0 && (
            <ExportButton
              filename={`vigia_municipio_${muni.cod_municipio}.csv`}
              cols={[
                { key: "categoria", label: "Categoría" },
                { key: "naturaleza", label: "Naturaleza" },
                { key: "total", label: "Total" },
              ]}
              rows={(detalle ?? []).map((d) => ({ categoria: prettyCat(d.categoria), naturaleza: d.naturaleza, total: d.total }))}
            />
          )}
          {onVerInforme && (
            <button className="ghost" onClick={() => onVerInforme(muni.cod_municipio)}>
              <Icon name="file-text" size={15} /> Generar informe
            </button>
          )}
          {onVerPronostico && (
            <button className="primary" onClick={() => onVerPronostico(muni.cod_municipio)}>
              <Icon name="trending-up" size={15} /> Ver pronóstico
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
