const TOKEN_KEY = "supportai.access_token";
const USER_KEY = "supportai.user";

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function saveSession(token: string, user: unknown): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getStoredUser<T>(): T | null {
  const value = sessionStorage.getItem(USER_KEY);
  if (!value) return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}
