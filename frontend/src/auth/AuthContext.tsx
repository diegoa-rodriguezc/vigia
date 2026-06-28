import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from "react";
import { login as apiLogin, logout as apiLogout, getMe, type AuthUser } from "../api";
import { AUTH_EVENT, isAuthenticated } from "./tokens";
import LoginModal from "../components/LoginModal";

interface AuthState {
  user: AuthUser | null;
  authenticated: boolean;
  ready: boolean; // ya se resolvió la sesión inicial (para evitar parpadeos)
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  openLogin: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);

  // Sesión inicial: si hay token, validarlo contra /auth/me.
  useEffect(() => {
    if (!isAuthenticated()) { setReady(true); return; }
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
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

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  const openLogin = useCallback(() => setLoginOpen(true), []);

  return (
    <AuthContext.Provider
      value={{ user, authenticated: !!user, ready, login, logout, openLogin }}
    >
      {children}
      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
