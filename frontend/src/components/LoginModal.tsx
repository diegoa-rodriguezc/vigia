import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "./icons";

// Modal de inicio de sesión. Se usa para acceder a las funciones de IA (Pronóstico y
// Asistente); el resto del tablero es de acceso público.
export default function LoginModal({ onClose }: { onClose: () => void }) {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const userRef = useRef<HTMLInputElement>(null);

  useEffect(() => { userRef.current?.focus(); }, []);

  // Cerrar con Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      await login(username.trim(), password);
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 401) setError("Usuario o contraseña incorrectos.");
      else if (status === 429) setError("Demasiados intentos. Espera unos minutos.");
      else setError(err?.response?.data?.error ?? "No se pudo iniciar sesión.");
      setLoading(false);
    }
  };

  return (
    <div className="auth-overlay" onMouseDown={onClose}>
      <div
        className="auth-modal card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="auth-head">
          <span className="logo" role="img" aria-label="VigIA"><Icon name="shield" size={20} /></span>
          <h2 id="login-title" style={{ margin: 0 }}>Iniciar sesión</h2>
          <button className="ghost auth-close" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
        <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
          El acceso es necesario para el pronóstico y el asistente. El resto del tablero es público.
        </p>

        <form onSubmit={submit}>
          <label className="field" style={{ marginBottom: 10 }}>
            Usuario
            <input
              ref={userRef}
              value={username}
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label className="field" style={{ marginBottom: 14 }}>
            Contraseña
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          {error && (
            <p className="muted" style={{ color: "var(--danger, #f87171)", display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="alert-triangle" size={15} /> {error}
            </p>
          )}

          <button className="primary" type="submit" disabled={loading} style={{ width: "100%", justifyContent: "center", marginTop: 4 }}>
            {loading ? "Entrando…" : <><Icon name="shield" size={15} /> Entrar</>}
          </button>
        </form>
      </div>
    </div>
  );
}
