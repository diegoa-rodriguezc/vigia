// Componentes de UI compartidos (sin dependencias externas).
import { Component, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon } from "./icons";

// ── Error boundary ──
// Aísla fallos de render de una vista para que no dejen toda la app en blanco.
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: unknown) { console.error("VigIA UI error:", error, info); }
  private retry = () => this.setState({ error: null });
  render() {
    if (this.state.error) {
      return (
        <div className="empty-state">
          <span className="empty-ic"><Icon name="alert-triangle" size={28} /></span>
          Ocurrió un error al mostrar esta vista.
          <div className="muted" style={{ marginTop: 8 }}>{this.state.error.message}</div>
          <button className="ghost" style={{ marginTop: 14 }} onClick={this.retry}>
            <Icon name="refresh" size={15} /> Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Formato de número en español de Colombia (separador de miles con punto),
// para que todas las cifras del tablero se vean igual.
export const nfmt = (n: number) => n.toLocaleString("es-CO");

// Formato decimal es-CO (coma decimal) con un número fijo de decimales; sin él,
// `toFixed` pinta el punto inglés y en una misma tabla el punto significaría dos cosas.
export const dfmt = (n: number, dec = 1) =>
  n.toLocaleString("es-CO", { minimumFractionDigits: dec, maximumFractionDigits: dec });

// Presenta un código de categoría de forma legible (HURTO_AUTOMOTORES → Hurto automotores).
export const prettyCat = (c: string) =>
  c.replace(/_/g, " ").toLowerCase().replace(/^\w/, (m) => m.toUpperCase());

// ── Exportar a CSV ──
// Sin dependencias: serializa un arreglo de objetos a CSV y dispara la descarga.
export interface CsvCol { key: string; label: string }

export function toCSV(rows: Record<string, unknown>[], cols: CsvCol[]): string {
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.map((c) => esc(c.label)).join(",");
  const body = rows.map((r) => cols.map((c) => esc(r[c.key])).join(",")).join("\n");
  return `${header}\n${body}`;
}

export function downloadCSV(filename: string, rows: Record<string, unknown>[], cols: CsvCol[]) {
  // BOM (﻿) para que Excel interprete UTF-8 y respete tildes/ñ.
  const blob = new Blob(["﻿" + toCSV(rows, cols)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Botón de descarga CSV. `rows` puede ser un arreglo (datos en cliente) o una función
// asíncrona que los obtiene al hacer clic (p. ej. para traer todo lo filtrado del servidor).
export function ExportButton({
  filename, rows, cols, label = "CSV",
}: {
  filename: string;
  rows: Record<string, unknown>[] | (() => Promise<Record<string, unknown>[]>);
  cols: CsvCol[];
  label?: string;
}) {
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const data = typeof rows === "function" ? await rows() : rows;
      if (data.length) downloadCSV(filename, data, cols);
    } finally {
      setBusy(false);
    }
  };
  const empty = Array.isArray(rows) && rows.length === 0;
  return (
    <button
      className="ghost export-btn"
      onClick={onClick}
      disabled={busy || empty}
      aria-label={`Descargar ${label}`}
      title="Descargar CSV"
    >
      <Icon name="download" size={14} /> {busy ? "Exportando…" : label}
    </button>
  );
}

// ── Región viva para lectores de pantalla ──
// Anuncia cambios de estado asíncrono (cargando, resultado, error) sin alterar el layout,
// para que las personas usuarias de lector de pantalla no queden sin retroalimentación.
export function LiveRegion({ message, assertive = false }: { message: string; assertive?: boolean }) {
  return (
    <div
      className="sr-only"
      role="status"
      aria-live={assertive ? "assertive" : "polite"}
      aria-atomic="true"
    >
      {message}
    </div>
  );
}

// ── KPI tile ──
export function StatTile({
  label, value, hint, icon, loading, tone = "accent",
}: {
  label: string; value: React.ReactNode; hint?: string; icon?: ReactNode;
  loading?: boolean; tone?: "accent" | "danger" | "warn";
}) {
  return (
    <div className="kpi">
      <div className="kpi-top">
        <div className="kpi-label">{label}</div>
        {icon && <span className={`kpi-ic ${tone}`}>{icon}</span>}
      </div>
      {loading
        ? <div className="skeleton" style={{ height: 30, width: "55%", marginTop: 12 }} />
        : <div className="kpi-value">{value}</div>}
      {hint && !loading && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

// ── Skeleton de filas para tablas ──
export function SkeletonRows({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: cols }).map((__, j) => (
            <td key={j}><div className="skeleton" style={{ height: 14, width: j === 0 ? "70%" : "45%" }} /></td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

// ── Tooltip temático para recharts ──

// Valor de una fila del tooltip. Una serie de RANGO (p. ej. la banda de incertidumbre del
// pronóstico) trae el valor como par [inferior, superior]: sin este caso, React concatenaría
// el arreglo sin separador («112.73140.12»).
export const tipValue = (v: unknown) =>
  Array.isArray(v) ? `${nfmt(v[0])} – ${nfmt(v[1])}` : typeof v === "number" ? nfmt(v) : v;

export function ChartTooltip({ active, payload, label, suffix = "" }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      {label != null && <div className="t-label">{label}</div>}
      {payload.map((p: any, i: number) => (
        p.value == null ? null : (
          <div className="t-row" key={i}>
            <span className="swatch" style={{ background: p.color || p.stroke || p.fill }} />
            <span>{p.name}:</span>
            <b>{tipValue(p.value)}{suffix}</b>
          </div>
        )
      ))}
    </div>
  );
}

// ── Paginación (cliente) ──
// Lógica pura (sin React) de paginado: clampa la página al rango válido y corta la
// página. Separada del hook para poder probarla sin montar componentes.
export function paginate<T>(items: T[], page: number, pageSize: number) {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    page: safePage,
    total,
    totalPages,
    from: total === 0 ? 0 : start + 1,
    to: Math.min(start + pageSize, total),
    pageItems: items.slice(start, start + pageSize),
  };
}

// Hook reutilizable: parte un arreglo ya filtrado/ordenado en páginas. `resetKey`
// (p. ej. el texto del filtro) regresa a la primera página cuando cambia el conjunto.
export function usePagination<T>(items: T[], initialSize = 10, resetKey?: unknown) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialSize);

  useEffect(() => { setPage(1); }, [resetKey, pageSize]);

  return { ...paginate(items, page, pageSize), setPage, pageSize, setPageSize };
}

// Ventana compacta de números de página con elipsis: 1 … 4 5 6 … 20
export function pageWindow(page: number, totalPages: number): (number | "…")[] {
  const keep = new Set([1, totalPages, page, page - 1, page + 1]);
  const nums = [...keep].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  let prev = 0;
  for (const p of nums) {
    if (prev && p - prev > 1) out.push("…");
    out.push(p);
    prev = p;
  }
  return out;
}

export function Pagination({
  page, totalPages, total, from, to, pageSize, onPage, onSize, sizes = [10, 25, 50],
}: {
  page: number; totalPages: number; total: number; from: number; to: number;
  pageSize: number; onPage: (p: number) => void; onSize?: (s: number) => void; sizes?: number[];
}) {
  if (total === 0) return null;
  return (
    <div className="pagination">
      <span className="pg-info">{nfmt(from)}-{nfmt(to)} de {nfmt(total)}</span>
      <div className="pg-controls" role="navigation" aria-label="Paginación">
        <button className="ghost pg-btn" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Página anterior">‹</button>
        {pageWindow(page, totalPages).map((p, i) =>
          p === "…"
            ? <span key={`e${i}`} className="pg-ellipsis">…</span>
            : <button
                key={p}
                className={`pg-btn ${p === page ? "primary" : "ghost"}`}
                aria-current={p === page ? "page" : undefined}
                onClick={() => onPage(p)}
              >{p}</button>,
        )}
        <button className="ghost pg-btn" disabled={page >= totalPages} onClick={() => onPage(page + 1)} aria-label="Página siguiente">›</button>
      </div>
      {onSize && (
        <label className="pg-size">
          Filas
          <select value={pageSize} onChange={(e) => onSize(Number(e.target.value))}>
            {sizes.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      )}
    </div>
  );
}

// ── Combobox con búsqueda (para listas largas, p. ej. 1.119 municipios) ──
export interface ComboItem { value: string; label: string; sub?: string }

export function Combobox({
  items, value, onChange, placeholder = "Buscar…", ariaLabel,
}: { items: ComboItem[]; value: string; onChange: (v: string) => void; placeholder?: string; ariaLabel?: string }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hi, setHi] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  // ids estables para enlazar input ↔ listbox ↔ opción activa (patrón ARIA combobox).
  const listId = useId();
  const optId = (idx: number) => `${listId}-opt-${idx}`;

  const selected = items.find((i) => i.value === value);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = q
      ? items.filter((i) => i.label.toLowerCase().includes(q) || i.sub?.toLowerCase().includes(q))
      : items;
    return base.slice(0, 50);
  }, [items, query]);

  const pick = (v: string) => { onChange(v); setOpen(false); setQuery(""); };

  return (
    <div className="combo" ref={ref}>
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && filtered[hi] ? optId(hi) : undefined}
        aria-label={ariaLabel}
        value={open ? query : (selected?.label ?? "")}
        placeholder={selected ? selected.label : placeholder}
        onFocus={() => { setOpen(true); setQuery(""); setHi(0); }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setHi(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, filtered.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
          else if (e.key === "Enter" && filtered[hi]) { e.preventDefault(); pick(filtered[hi].value); }
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <div className="combo-list" id={listId} role="listbox" aria-label={ariaLabel}>
          {filtered.length === 0 && <div className="combo-empty">Sin resultados</div>}
          {filtered.map((i, idx) => (
            <div
              key={i.value}
              id={optId(idx)}
              role="option"
              aria-selected={idx === hi}
              className={`combo-opt ${idx === hi ? "active" : ""}`}
              onMouseEnter={() => setHi(idx)}
              onMouseDown={(e) => { e.preventDefault(); pick(i.value); }}
            >
              {i.label}{i.sub && <span className="sub"> · {i.sub}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
