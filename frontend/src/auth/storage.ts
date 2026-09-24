const TOKEN_KEY = "aiderai.access_token";
const USER_KEY = "aiderai.user";
const LEGACY_TOKEN_KEY = "supportai.access_token";
const LEGACY_USER_KEY = "supportai.user";

function migrateLegacyValue(key: string, legacyKey: string): string | null {
  const currentValue = sessionStorage.getItem(key);
  if (currentValue !== null) return currentValue;

  const legacyValue = sessionStorage.getItem(legacyKey);
  if (legacyValue === null) return null;

  sessionStorage.setItem(key, legacyValue);
  sessionStorage.removeItem(legacyKey);
  return legacyValue;
}

export function getAccessToken(): string | null {
  return migrateLegacyValue(TOKEN_KEY, LEGACY_TOKEN_KEY);
}

export function saveSession(token: string, user: unknown): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  sessionStorage.removeItem(LEGACY_USER_KEY);
}

export function getStoredUser<T>(): T | null {
  const value = migrateLegacyValue(USER_KEY, LEGACY_USER_KEY);
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as T;
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "email" in parsed &&
      parsed.email === "demo@supportai.local"
    ) {
      const migrated = { ...parsed, email: "demo@aiderai.local" } as T;
      sessionStorage.setItem(USER_KEY, JSON.stringify(migrated));
      return migrated;
    }
    return parsed;
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  sessionStorage.removeItem(LEGACY_USER_KEY);
}
