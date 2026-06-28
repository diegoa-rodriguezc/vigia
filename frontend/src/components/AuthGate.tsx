import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "./icons";

// Envuelve una vista que requiere sesión. Si el usuario no está autenticado, muestra un
// aviso con botón de acceso en vez del contenido (el resto del tablero sigue público).
export default function AuthGate({ feature, children }: { feature: string; children: ReactNode }) {
  const { authenticated, ready, openLogin } = useAuth();

  if (!ready) return <div className="skeleton" style={{ height: 240 }} />;
  if (authenticated) return <>{children}</>;

  return (
    <div className="empty-state">
      <span className="empty-ic"><Icon name="shield" size={28} /></span>
      Inicia sesión para usar {feature}.
      <div className="muted" style={{ marginTop: 6 }}>
        Es una función con cómputo de IA, protegida frente a abuso. El resto del tablero es de acceso público.
      </div>
      <button className="primary" style={{ marginTop: 14 }} onClick={openLogin}>
        <Icon name="shield" size={15} /> Iniciar sesión
      </button>
    </div>
  );
}
