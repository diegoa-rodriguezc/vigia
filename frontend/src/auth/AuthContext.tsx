import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from "react";
import {
  login as apiLogin, register as apiRegister, logout as apiLogout, getMe, getConfig,
  type AuthUser,
} from "../api";
import { AUTH_EVENT, isAuthenticated } from "./tokens";
import LoginModal from "../components/LoginModal";

// Modo del modal de acceso: iniciar sesión o crear una cuenta ciudadana.
export type AuthMode = "login" | "register";

interface AuthState {
  user: AuthUser | null;
  authenticated: boolean;
  ready: boolean; // ya se resolvió la sesión inicial (para evitar parpadeos)
  registrationEnabled: boolean; // el backend permite crear cuentas (feature flag de runtime)
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  openLogin: (mode?: AuthMode) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [registrationEnabled, setRegistrationEnabled] = useState(true);

  // Sesión inicial: si hay token, validarlo contra /auth/me.
  useEffect(() => {
    if (!isAuthenticated()) { setReady(true); return; }
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  // Feature flags del backend (p. ej. si el registro está habilitado). Ante fallo, se asume
  // habilitado (comportamiento por defecto); la validación que decide vive en el servidor.
  useEffect(() => {
    getConfig()
      .then((c) => setRegistrationEnabled(c.registration_enabled))
      .catch(() => setRegistrationEnabled(true));
  }, []);

  // Si los tokens se limpian en otro lugar (p. ej. el interceptor tras un refresh
  // fallido), refleja el cierre de sesión en la UI.
  useEffect(() => {
    const onChange = () => { if (!isAuthenticated()) setUser(null); };
    window.addEventListener(AUTH_EVENT, onChange);
    return () => window.removeEventListener(AUTH_EVENT, onChange);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const u = await apiLogin(username, password);
    setUser(u);
    setLoginOpen(false);
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    const u = await apiRegister(username, password);
    setUser(u);
    setLoginOpen(false);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  const openLogin = useCallback((mode: AuthMode = "login") => {
    setAuthMode(mode);
    setLoginOpen(true);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, authenticated: !!user, ready, registrationEnabled, login, register, logout, openLogin }}
    >
      {children}
      {loginOpen && <LoginModal initialMode={authMode} onClose={() => setLoginOpen(false)} />}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
