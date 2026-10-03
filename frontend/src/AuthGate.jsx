import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import App from "./App.jsx";
import "./AuthGate.css";

/*
  Authentication layer around the existing dashboard.

  - The session lives in an HttpOnly cookie that the BACKEND sets. JavaScript
    cannot read it, and nothing secret is stored in localStorage / sessionStorage.
  - The only thing typed here is the password, held in component state just
    long enough to POST it to /auth/login.
  - No API key exists in the frontend. The browser authenticates with the cookie only.
  - The real enforcement is in FastAPI; this screen only decides what to show.
*/

const API = import.meta.env.VITE_API_URL;

// Send the session cookie on every request to the backend (cross-site: Vercel -> Render).
axios.defaults.withCredentials = true;

// If the session expires while the dashboard is open, any 401 sends the user back to login.
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = String(error?.config?.url || "");
    if (error?.response?.status === 401 && !url.includes("/auth/")) {
      window.dispatchEvent(new Event("auth:expired"));
    }
    return Promise.reject(error);
  }
);

const detailOf = (err) =>
  typeof err?.response?.data?.detail === "string" ? err.response.data.detail : "";

// Asks the backend whether the cookie in this browser is a valid session.
async function fetchSessionStatus() {
  try {
    await axios.get(`${API}/auth/me`);
    return { status: "loggedIn", notice: "" };
  } catch (err) {
    const code = err?.response?.status;
    if (code === 401) return { status: "loggedOut", notice: "" };
    if (!err?.response) return { status: "unreachable", notice: "" };
    return { status: "serverError", notice: detailOf(err) };
  }
}

export default function AuthGate() {
  // "checking" | "loggedOut" | "loggedIn" | "unreachable" | "serverError"
  const [status, setStatus] = useState("checking");
  const [notice, setNotice] = useState("");

  const applyCheck = useCallback((result) => {
    setNotice(result.notice);
    setStatus(result.status);
  }, []);

  useEffect(() => {
    let alive = true;
    fetchSessionStatus().then((result) => alive && applyCheck(result));
    return () => { alive = false; };
  }, [applyCheck]);

  useEffect(() => {
    const onExpired = () => {
      setNotice("Your session has expired. Please log in again.");
      setStatus("loggedOut");
    };
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, []);

  const logout = useCallback(async () => {
    try {
      await axios.post(`${API}/auth/logout`);
    } catch (err) {
      console.error("Logout request failed:", err);
    }
    setNotice("");
    setStatus("loggedOut"); // unmounts the dashboard, which drops all email data from memory
  }, []);

  if (status === "loggedIn") return <App onLogout={logout} />;

  if (status === "checking") {
    return (
      <div className="auth-wrap">
        <div className="auth-card"><p className="auth-sub">Checking your session…</p></div>
      </div>
    );
  }

  if (status === "unreachable" || status === "serverError") {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>Can't connect</h1>
          <p className="auth-err" role="alert">
            {status === "unreachable"
              ? "Cannot reach the backend. Check your connection and try again. (The server may be waking up; this can take a minute.)"
              : `Backend/server error${notice ? `: ${notice}` : ""}`}
          </p>
          <button
            className="btn p auth-btn"
            onClick={() => { setStatus("checking"); fetchSessionStatus().then(applyCheck); }}
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <LoginForm
      notice={notice}
      onSuccess={() => {
        setNotice("");
        setStatus("loggedIn");
      }}
    />
  );
}

function LoginForm({ notice, onSuccess }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (busy || !password) return;
    setBusy(true);
    setError("");
    try {
      await axios.post(`${API}/auth/login`, { password });
      setPassword("");
      onSuccess();
    } catch (err) {
      const code = err?.response?.status;
      if (code === 401) setError("Incorrect password.");
      else if (code === 403) setError("You are not authorized.");
      else if (code === 429) setError(detailOf(err) || "Too many attempts. Try again later.");
      else if (code >= 500) setError(`Backend/server error${detailOf(err) ? `: ${detailOf(err)}` : ""}`);
      else if (!err?.response) setError("Cannot reach the backend. Check your connection and try again.");
      else setError("Login failed.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1>Personal AI Email Manager</h1>
        <p className="auth-sub">Please log in to see your emails.</p>
        {notice && !error && <p className="auth-note" role="status">{notice}</p>}
        <label htmlFor="pw">Password</label>
        <input
          id="pw"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
        />
        {error && <p className="auth-err" role="alert">{error}</p>}
        <button className="btn p auth-btn" type="submit" disabled={busy || !password}>
          {busy ? "Logging in…" : "Log in"}
        </button>
      </form>
    </div>
  );
}
