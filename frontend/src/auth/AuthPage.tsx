import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/http";
import type { AuthResponse } from "../api/types";
import { useAuth } from "./AuthProvider";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { token, completeAuthentication } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (token) return <Navigate to="/chat" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const payload = mode === "login" ? { email, password } : { email, password, name };
      const response = await apiRequest<AuthResponse>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      completeAuthentication(response);
      navigate("/chat", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to connect. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const isLogin = mode === "login";
  return (
    <main className="auth-shell">
      <section className="auth-brand" aria-label="SupportAI overview">
        <Link className="brand" to="/">SupportAI</Link>
        <p className="eyebrow">AI customer care workspace</p>
        <h2>Resolve every request with context and confidence.</h2>
        <p>Grounded answers, safe account actions, and a clear history for every conversation.</p>
      </section>
      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <p className="eyebrow">{isLogin ? "Secure sign in" : "Get started"}</p>
          <h1>{isLogin ? "Welcome back" : "Create your account"}</h1>
          <p className="muted">
            {isLogin ? "Continue to your support workspace." : "Set up your SupportAI workspace."}
          </p>
          {!isLogin && (
            <label>
              Full name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={10} required />
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? "Please wait…" : isLogin ? "Sign in" : "Create account"}
          </button>
          <p className="auth-switch">
            {isLogin ? "New to SupportAI?" : "Already have an account?"}{" "}
            <Link to={isLogin ? "/register" : "/login"}>{isLogin ? "Create an account" : "Sign in"}</Link>
          </p>
        </form>
      </section>
    </main>
  );
}
