import { useEffect, useRef, useState } from "react";
import { useAuth, type AuthMode } from "../auth/AuthContext";
import { Icon } from "./icons";

// Modal de acceso: inicia sesión o crea una cuenta ciudadana. Las funciones de IA (Pronóstico,
// Simulador, Asistente e Informe) requieren sesión; el resto del tablero es de acceso público.
// La ciudadanía puede registrarse aquí y usar el asistente sin depender de la cuenta admin.
export default function LoginModal({
  onClose,
  initialMode = "login",
}: {
  onClose: () => void;
  initialMode?: AuthMode;
}) {
  const { login, register, registrationEnabled } = useAuth();
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const userRef = useRef<HTMLInputElement>(null);

  // Si el backend deshabilitó el registro, nunca se muestra el modo "crear cuenta"
  // (aunque se abriera con ese modo): solo inicio de sesión.
  const isRegister = registrationEnabled && mode === "register";

  useEffect(() => { userRef.current?.focus(); }, []);

  // Cerrar con Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const switchMode = () => {
    setMode(isRegister ? "login" : "register");
    setError(null);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      if (isRegister) await register(username.trim(), password);
      else await login(username.trim(), password);
    } catch (err: any) {
      const status = err?.response?.status;
      const serverMsg = err?.response?.data?.error;
      if (isRegister) {
        // 400 = política de contraseña / usuario inválido (mensaje del backend); 409 = ya existe.
        if (status === 409) setError("Ese nombre de usuario ya está en uso.");
        else if (status === 400 && serverMsg) setError(serverMsg);
        else if (status === 429) setError("Demasiados intentos. Espere unos minutos.");
        else setError(serverMsg ?? "No se pudo crear la cuenta.");
      } else {
        if (status === 401) setError("Usuario o contraseña incorrectos.");
        else if (status === 429) setError("Demasiados intentos. Espere unos minutos.");
        else setError(serverMsg ?? "No se pudo iniciar sesión.");
      }
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
          <h2 id="login-title" style={{ margin: 0 }}>
            {isRegister ? "Crear cuenta" : "Iniciar sesión"}
          </h2>
          <button className="ghost auth-close" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
        <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
          {isRegister
            ? "Cree una cuenta ciudadana para usar el pronóstico, el simulador, el asistente y el informe. El resto del tablero es público."
            : "El acceso es necesario para el pronóstico, el simulador, el asistente y el informe. El resto del tablero es público."}
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
          <label className="field" style={{ marginBottom: isRegister ? 6 : 14 }}>
            Contraseña
            <input
              type="password"
              value={password}
              autoComplete={isRegister ? "new-password" : "current-password"}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {isRegister && (
            <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: "0.78rem" }}>
              Mínimo 12 caracteres, con mayúscula, minúscula, dígito y símbolo.
            </p>
          )}

          {error && (
            <p className="muted" style={{ color: "var(--danger, #f87171)", display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="alert-triangle" size={15} /> {error}
            </p>
          )}

          <button className="primary" type="submit" disabled={loading} style={{ width: "100%", justifyContent: "center", marginTop: 4 }}>
            {loading
              ? (isRegister ? "Creando…" : "Entrando…")
              : (isRegister
                  ? <><Icon name="shield" size={15} /> Crear cuenta</>
                  : <><Icon name="shield" size={15} /> Entrar</>)}
          </button>
        </form>

        {registrationEnabled && (
          <p className="muted" style={{ marginTop: 14, marginBottom: 0, fontSize: "0.85rem", textAlign: "center" }}>
            {isRegister ? "¿Ya tiene cuenta? " : "¿No tiene cuenta? "}
            <button
              type="button"
              className="ghost"
              onClick={switchMode}
              style={{ padding: 0, textDecoration: "underline", cursor: "pointer" }}
            >
              {isRegister ? "Inicie sesión" : "Crear una cuenta"}
            </button>
          </p>
        )}
      </div>
    </div>
  );
}
