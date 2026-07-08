import { useEffect, useRef, useState } from "react";
import { askAssistant, type Fuente } from "../api";
import { LiveRegion } from "./ui";
import { Icon } from "./icons";

interface Mensaje { rol: "user" | "bot"; texto: string; fuentes?: Fuente[]; error?: boolean; }

// Etiqueta legible de una fuente recuperada según su tipo.
function sourceLabel(f: Fuente): string {
  const md = f.metadata as Record<string, string>;
  switch (md.tipo) {
    case "municipio": return `Municipio: ${md.municipio}`;
    case "categoria": return `Delito: ${md.categoria}`;
    case "ranking": return `Ranking: ${md.categoria}`;
    case "pronostico": return `Pronóstico: ${md.categoria}`;
    case "administrativo": return `Gestión: ${md.fuente}`;
    case "documento": return md.pagina ? `Documento: ${md.fuente} (pág. ${md.pagina})` : `Documento: ${md.fuente}`;
    case "contexto": return "Contexto VigIA";
    default: return "dato";
  }
}

const SUGERENCIAS = [
  "¿Cuáles son los delitos más frecuentes en Bogotá?",
  "¿Dónde hay más homicidios?",
  "¿Qué es VigIA y de dónde provienen los datos?",
  "¿Cómo ha evolucionado el homicidio en el país?",
];

export default function Asistente() {
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [anuncio, setAnuncio] = useState("");  // mensaje para el lector de pantalla
  const logRef = useRef<HTMLDivElement>(null);

  // Auto-scroll al último mensaje.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [mensajes, cargando]);

  const enviar = async (pregunta: string) => {
    if (!pregunta.trim() || cargando) return;
    setMensajes((m) => [...m, { rol: "user", texto: pregunta }]);
    setTexto("");
    setCargando(true);
    setAnuncio("Consultando el asistente, puede tardar uno o dos minutos.");
    try {
      const res = await askAssistant(pregunta);
      setMensajes((m) => [...m, { rol: "bot", texto: res.respuesta, fuentes: res.fuentes }]);
      setAnuncio(`Respuesta recibida: ${res.respuesta}`);
    } catch (e: any) {
      const msg = e?.response?.data?.error ?? e.message;
      setMensajes((m) => [...m, { rol: "bot", texto: `⚠️ Asistente no disponible: ${msg}`, error: true }]);
      setAnuncio(`El asistente no está disponible: ${msg}`);
    } finally {
      setCargando(false);
    }
  };

  return (
    <>
      <h2 className="section-title">Asistente ciudadano</h2>
      <p className="section-sub">Respuestas generadas con RAG sobre datos oficiales; cada respuesta cita sus fuentes.</p>
      <LiveRegion message={anuncio} />


      <div className="card">
        <div className="suggestions">
          {SUGERENCIAS.map((s) => (
            <button key={s} className="ghost" onClick={() => enviar(s)} disabled={cargando}>{s}</button>
          ))}
        </div>

        <div className="chat-log" ref={logRef} role="log" aria-label="Conversación con el asistente">
          {mensajes.length === 0 && !cargando && (
            <div className="empty-state">
              <span className="empty-ic"><Icon name="message" size={28} /></span>
              Pregunta sobre seguridad ciudadana. El asistente responde solo con datos oficiales.
            </div>
          )}
          {mensajes.map((m, i) => (
            <div key={i} className={`msg ${m.rol}${m.error ? " err" : ""}`}>
              <div>{m.texto}</div>
              {m.fuentes && m.fuentes.length > 0 && (
                <div className="sources">
                  {m.fuentes.map((f, j) => (
                    <span className="chip" key={j}><Icon name="database" size={12} /> {sourceLabel(f)}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {cargando && (
            <div className="msg bot">
              <span className="typing"><span /><span /><span /></span>
            </div>
          )}
        </div>

        <div className="row" style={{ marginBottom: 8 }}>
          <input
            style={{ flex: 1, minWidth: 240 }}
            value={texto}
            placeholder="Escribe tu pregunta sobre seguridad ciudadana…"
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && enviar(texto)}
          />
          <button className="primary" onClick={() => enviar(texto)} disabled={cargando || !texto.trim()}>
            <Icon name="send" size={15} /> Enviar
          </button>
        </div>
        <p className="muted" style={{ fontSize: "0.78rem", margin: 0 }}>
          Las respuestas se basan únicamente en datos abiertos oficiales y citan su fuente. Las cifras
          reflejan hechos registrados, no la criminalidad real. La respuesta la genera un modelo de lenguaje (LLM): con proveedor gestionado responde en unos segundos; con el modelo local en CPU puede tardar ~30-90 s.
        </p>
      </div>
    </>
  );
}
