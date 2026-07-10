import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "./icons";

// Envuelve una vista que requiere sesión. Si el usuario no está autenticado, muestra un
// aviso con botón de acceso en vez del contenido (el resto del tablero sigue público).
export default function AuthGate({ feature, children }: { feature: string; children: ReactNode }) {
  const { authenticated, ready, registrationEnabled, openLogin } = useAuth();

  if (!ready) return <div className="skeleton" style={{ height: 240 }} />;
  if (authenticated) return <>{children}</>;

  return (
    <div className="empty-state">
      <span className="empty-ic"><Icon name="shield" size={28} /></span>
      {registrationEnabled
        ? <>Inicie sesión o cree una cuenta para usar {feature}.</>
        : <>Inicie sesión para usar {feature}.</>}
      <div className="muted" style={{ marginTop: 6 }}>
        Es una función con cómputo de IA, protegida frente a abuso.{" "}
        {registrationEnabled && "El registro es gratuito; "}el resto del tablero es de acceso público.
      </div>
      <div style={{ marginTop: 14, display: "inline-flex", gap: 8 }}>
        <button className="primary" onClick={() => openLogin("login")}>
          <Icon name="shield" size={15} /> Iniciar sesión
        </button>
        {registrationEnabled && (
          <button className="ghost" onClick={() => openLogin("register")}>
            Crear cuenta
          </button>
        )}
      </div>
    </div>
  );
}
