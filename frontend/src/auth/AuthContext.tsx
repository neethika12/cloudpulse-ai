import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, setAuthToken, AuthUser } from "../api/client";

const TOKEN_STORAGE_KEY = "cloudpulse_token";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // On first load, if a token was saved from a previous session, restore it and
  // fetch the current user. If the token's expired or invalid, silently log out.
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    setAuthToken(stored);
    api
      .me()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setAuthToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const applyToken = async (accessToken: string) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
    setAuthToken(accessToken);
    const me = await api.me();
    setUser(me);
  };

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password);
    await applyToken(res.access_token);
  };

  const signup = async (email: string, password: string, fullName?: string) => {
    const res = await api.signup(email, password, fullName);
    await applyToken(res.access_token);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    const me = await api.me();
    setUser(me);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
