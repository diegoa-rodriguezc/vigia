// Almacenamiento de tokens de sesión (sin dependencias). El access token se envía como
// `Authorization: Bearer`; el refresh sirve para renovar el access cuando expira.
//
// Nota de seguridad: se guardan en localStorage para persistir entre recargas. Esto los
// expone a robo por XSS; se mitiga con la política de seguridad del backend (sin scripts
// de terceros) y la vida corta del access token. Una alternativa más estricta serían
// cookies httpOnly + CSRF (ver ADR de arquitectura).

const ACCESS_KEY = "vigia_access";
const REFRESH_KEY = "vigia_refresh";

// Evento que notifica a la app que el estado de sesión cambió (login/logout/expiración).
export const AUTH_EVENT = "vigia-auth-changed";

function emit() {
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
  emit();
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  emit();
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}
