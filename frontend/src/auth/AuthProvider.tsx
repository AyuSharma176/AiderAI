import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { AuthResponse, User } from "../api/types";
import { queryClient } from "../api/queryClient";
import { clearSession, getAccessToken, getStoredUser, saveSession } from "./storage";

interface AuthContextValue {
  token: string | null;
  user: User | null;
  completeAuthentication: (response: AuthResponse) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getAccessToken());
  const [user, setUser] = useState<User | null>(() => getStoredUser<User>());

  const logout = useCallback(() => {
    void queryClient.cancelQueries();
    queryClient.clear();
    clearSession();
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    window.addEventListener("supportai:unauthorized", logout);
    return () => window.removeEventListener("supportai:unauthorized", logout);
  }, [logout]);

  const completeAuthentication = useCallback((response: AuthResponse) => {
    queryClient.clear();
    saveSession(response.access_token, response.user);
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const value = useMemo(
    () => ({ token, user, completeAuthentication, logout }),
    [token, user, completeAuthentication, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
