import { lazy, Suspense, useEffect, useState } from "react";
import { ErrorBoundary } from "./components/ui";
import { Icon, type IconName } from "./components/icons";
import { getHealth } from "./api";
import { useAuth } from "./auth/AuthContext";
import AuthGate from "./components/AuthGate";

// Carga diferida por pestaña: cada vista (y sus dependencias pesadas, recharts/leaflet)
// se descarga solo al abrirla, reduciendo el bundle inicial.
const Panorama = lazy(() => import("./components/Panorama"));
const Forecast = lazy(() => import("./components/Forecast"));
const Simulador = lazy(() => import("./components/Simulador"));
const Alertas = lazy(() => import("./components/Alertas"));
const Asistente = lazy(() => import("./components/Asistente"));
const SaludModelo = lazy(() => import("./components/SaludModelo"));
const Justicia = lazy(() => import("./components/Justicia"));
const Informe = lazy(() => import("./components/Informe"));

type Tab = "panorama" | "alertas" | "justicia" | "pronostico" | "simulador" | "asistente" | "informe" | "salud";

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "panorama", label: "Panorama", icon: "dashboard" },
  { id: "alertas", label: "Alertas tempranas", icon: "bell" },
  { id: "justicia", label: "Justicia", icon: "layers" },
  { id: "pronostico", label: "Pronóstico", icon: "trending-up" },
  { id: "simulador", label: "Simulador", icon: "sliders" },
  { id: "asistente", label: "Asistente ciudadano", icon: "message" },
  { id: "informe", label: "Informe", icon: "file-text" },
  { id: "salud", label: "Salud del modelo", icon: "activity" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("panorama");
  const [online, setOnline] = useState<boolean | null>(null);
  const [preMuni, setPreMuni] = useState<string | null>(null);  // municipio del drill-down → pronóstico/informe
  const { authenticated, user, logout, openLogin } = useAuth();

  // Deep-links desde el drill-down del Panorama: preseleccionan el municipio y abren la vista.
  const verPronostico = (cod: string) => { setPreMuni(cod); setTab("pronostico"); };
  const verInforme = (cod: string) => { setPreMuni(cod); setTab("informe"); };

  useEffect(() => {
    getHealth()
      .then((h) => setOnline(h.db))
      .catch(() => setOnline(false));
  }, []);

  const statusClass = online == null ? "" : online ? "ok" : "down";
  const statusText = online == null ? "Conectando…" : online ? "Datos en línea" : "Sin datos";

  return (
    <>
      <a className="skip-link" href="#contenido">Saltar al contenido</a>
      <header className="app-header">
        <span className="logo" role="img" aria-label="VigIA"><Icon name="shield" size={24} /></span>
        <div>
          <h1>Vig<span className="ia">IA</span></h1>
          <div className="tag">IA para la Seguridad Ciudadana y la Justicia · Datos abiertos de Colombia</div>
        </div>
        <div className="spacer" />
        <span className={`status ${statusClass}`} title="Estado de la base de datos gold">
          <span className="dot" />{statusText}
        </span>
        {authenticated ? (
          <div className="auth-actions">
            <span className="auth-user" title={`Sesión: ${user?.username}`}>
              <Icon name="shield" size={14} /> {user?.username}
            </span>
            <button className="ghost auth-btn" onClick={() => logout()}>Cerrar sesión</button>
          </div>
        ) : (
          <button className="ghost auth-btn" onClick={openLogin}>
            <Icon name="shield" size={15} /> Iniciar sesión
          </button>
        )}
      </header>

      <nav
        className="tabs"
        role="tablist"
        aria-label="Vistas del tablero"
        onKeyDown={(e) => {
          // Navegación por flechas entre pestañas (patrón APG tabs).
          if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
          e.preventDefault();
          const i = TABS.findIndex((t) => t.id === tab);
          const next = e.key === "ArrowRight" ? (i + 1) % TABS.length : (i - 1 + TABS.length) % TABS.length;
          setTab(TABS[next].id);
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            role="tab"
            aria-selected={tab === t.id}
            aria-controls="contenido"
            tabIndex={tab === t.id ? 0 : -1}
            className={tab === t.id ? "active" : ""}
            onClick={() => setTab(t.id)}
          >
            <Icon name={t.icon} size={17} /> {t.label}
          </button>
        ))}
      </nav>

      <main
        className="content"
        id="contenido"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        tabIndex={0}
      >
        {/* key={tab} aísla y reinicia el error boundary al cambiar de vista. */}
        <ErrorBoundary key={tab}>
          <Suspense fallback={<div className="skeleton" style={{ height: 240 }} />}>
            {tab === "panorama" && <Panorama onVerPronostico={verPronostico} onVerInforme={verInforme} />}
            {tab === "alertas" && <Alertas />}
            {tab === "justicia" && <Justicia />}
            {tab === "pronostico" && <AuthGate feature="el pronóstico"><Forecast initialCod={preMuni} /></AuthGate>}
            {tab === "simulador" && <AuthGate feature="el simulador de escenarios"><Simulador /></AuthGate>}
            {tab === "asistente" && <AuthGate feature="el asistente ciudadano"><Asistente /></AuthGate>}
            {tab === "informe" && <AuthGate feature="el informe de seguridad"><Informe initialCod={preMuni} /></AuthGate>}
            {tab === "salud" && <SaludModelo />}
          </Suspense>
        </ErrorBoundary>
      </main>

      <footer className="app-footer">
        VigIA · Concurso Datos al Ecosistema 2026 · Seguridad Ciudadana y Justicia ·
        Fuentes: Entidades Públicas y DANE (DIVIPOLA) vía datos.gov.co ·
        Las cifras reflejan hechos registrados, no la criminalidad real.
      </footer>
    </>
  );
}
