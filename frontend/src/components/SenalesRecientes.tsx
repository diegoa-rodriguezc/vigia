import { useEffect, useState } from "react";
import { getRealtimeDepto, type RealtimeSignal } from "../api";
import { Icon } from "./icons";

// Panel de "Señales recientes": noticias de prensa en tiempo real, como complemento —no
// sustituto— del dato oficial mensual. Se etiqueta explícitamente que NO son cifras oficiales.
// Feed nacional por defecto; al seleccionar un departamento en el mapa, se filtra a ese.
export default function SenalesRecientes({
  cod,
  nombre,
  onClear,
}: {
  cod?: string;        // undefined = nacional
  nombre?: string;     // nombre del departamento seleccionado (para el título)
  onClear?: () => void; // volver al feed nacional
}) {
  const [data, setData] = useState<RealtimeSignal | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let vivo = true;
    setLoading(true);
    setErr(false);
    getRealtimeDepto(cod)
      .then((d) => { if (vivo) setData(d); })
      .catch(() => { if (vivo) setErr(true); })
      .finally(() => { if (vivo) setLoading(false); });
    return () => { vivo = false; };
  }, [cod]);

  const titulo = cod ? (nombre ?? data?.departamento ?? "Departamento") : "Nacional";

  return (
    <div className="card senales" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 440 }}>
      <h3><Icon name="bell" /> Señales recientes</h3>
      <div className="card-sub" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span>Prensa · <b>{titulo}</b></span>
        {cod && onClear && (
          <button className="ghost" style={{ padding: "0 6px", fontSize: "0.78rem" }} onClick={onClear}>
            ← Nacional
          </button>
        )}
      </div>

      {/* El área de scroll va en posición absoluta para que la lista (contenido variable)
          NO infle la altura de la fila: así el MAPA fija la altura y el panel se estira
          hasta él. */}
      <div style={{ position: "relative", flex: 1, minHeight: 0, marginTop: 8 }}>
        <div style={{ position: "absolute", inset: 0, overflowY: "auto" }}>
          {loading ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : err ? (
            <div className="table-empty">No se pudo cargar la señal de prensa.</div>
          ) : data?.nota || (data && data.items.length === 0) ? (
            <div className="table-empty">{data?.nota ?? "Sin noticias recientes para este territorio."}</div>
          ) : (
            <ul className="senales-list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {data?.items.map((it, i) => (
                <li key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <a href={it.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.86rem", lineHeight: 1.35 }}>
                    {it.titulo}
                  </a>
                  <div className="muted" style={{ fontSize: "0.72rem", marginTop: 3 }}>
                    {it.fuente} · {it.fecha}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="muted" style={{ fontSize: "0.7rem", marginTop: 8, marginBottom: 0 }}>
        <Icon name="alert-triangle" size={12} /> Noticias de prensa, señal en tiempo real —
        <b> no son cifras oficiales</b> de criminalidad.
      </p>
    </div>
  );
}
