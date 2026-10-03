import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

const API = import.meta.env.VITE_API_URL;

/* ---------- small UI helpers ---------- */
const P = {
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3 8 9 6 9-6"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  tag: '<path d="M20 12 12 20 4 12V4h8z"/><circle cx="8.5" cy="8.5" r="1"/>',
  moon: '<path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  alert: '<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
};
const Icon = ({ n, s = 16 }) => (
  <svg className="ic" viewBox="0 0 24 24" width={s} height={s} aria-hidden="true" dangerouslySetInnerHTML={{ __html: P[n] }} />
);
const AIBadge = ({ children }) => (
  <span className="ai"><Icon n="spark" s={12} />{children}</span>
);
// Say what is really wrong instead of always blaming "the backend is not running".
const errorMessage = (err, fallback) => {
  const code = err?.response?.status;
  const detail = typeof err?.response?.data?.detail === "string" ? err.response.data.detail : "";
  if (code === 401) return "Please log in";
  if (code === 403) return "You are not authorized";
  if (code >= 500) return `Backend/server error${detail ? `: ${detail}` : ""}`;
  if (!err?.response) return "Cannot reach the backend. Check your connection and that the server is running.";
  return detail || fallback;
};
const cap = (s = "") => s.charAt(0).toUpperCase() + s.slice(1);
const fmtDate = (d) => {
  if (!d) return "";
  const x = new Date(d);
  return Number.isNaN(x.getTime()) ? String(d) : x.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};
const Priority = ({ value }) => <span className={`pri ${value || "unknown"}`}>{cap(value || "unknown")}</span>;
const Skeleton = ({ rows = 3 }) => (
  <div className="skwrap">{Array.from({ length: rows }, (_, i) => <div key={i} className="sk" style={{ width: `${95 - i * 12}%` }} />)}</div>
);

function BriefingText({ text }) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return (
    <div className="bt">
      {lines.map((l, i) => {
        const bullet = /^[-*•]\s+/.test(l);
        const t = l.replace(/^[-*•]\s+/, "").replace(/^#+\s*/, "").replace(/\*\*/g, "");
        if (bullet) return <p key={i} className="bl">{t}</p>;
        if (/^#+\s/.test(l) || (t.endsWith(":") && t.length < 48)) return <h3 key={i}>{t.replace(/:$/, "")}</h3>;
        return <p key={i}>{t}</p>;
      })}
    </div>
  );
}

const NAV = [
  ["all", "inbox", "All mail"],
  ["high", "flag", "Important"],
  ["unread", "mail", "Unread"],
];
const AI_NAV = [
  ["action", "check", "Action required"],
  ["deadlines", "clock", "Deadlines"],
];
const CATEGORIES = ["internship", "placement", "job", "recruitment", "education", "finance", "promotion"];
const TITLES = {
  all: ["All mail", "Every email AI has organized for you"],
  high: ["Important", "Emails the AI marked high priority"],
  unread: ["Unread", "Emails you have not opened yet"],
  action: ["Action required", "Emails waiting on you"],
  deadlines: ["Deadlines", "Emails with a date attached"],
};

function App({ onLogout }) {
  // ---------- STATE (unchanged) ----------
  const [emails, setEmails] = useState([]);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [briefing, setBriefing] = useState("");
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const knownEmailIds = useRef(new Set());
  const notificationInitialized = useRef(false);

  // ---------- NEW UI STATE ----------
  const [menuOpen, setMenuOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [briefingError, setBriefingError] = useState(false);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
    catch { return "light"; }
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch { /* storage unavailable */ }
  }, [theme]);

  const toast = useCallback((message, kind = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3000);
  }, []);

  // ---------- NOTIFICATIONS (unchanged) ----------
  const requestNotificationPermission = useCallback(async () => {
    if (!("Notification" in window)) return;
    if (Notification.permission === "default") {
      try { await Notification.requestPermission(); }
      catch (err) { console.error("Notification permission failed:", err); }
    }
  }, []);

  const notifyNewEmails = useCallback((newEmails) => {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    newEmails.forEach((email) => {
      if (!email?.id) return;
      if (knownEmailIds.current.has(email.id)) return;
      const isImportant =
        email.priority === "high" || email.action_required === true ||
        ["internship", "placement", "job", "recruitment"].includes(email.category);
      knownEmailIds.current.add(email.id);
      if (!isImportant) return;
      new Notification("🤖 Important Email", {
        body: `${email.subject || "New important email"}\n${email.summary || "Requires your attention."}`,
        icon: "/favicon.ico",
      });
    });
  }, []);

  // ---------- LOAD EMAILS (unchanged) ----------
  const loadEmails = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const response = await axios.get(`${API}/emails/`);
      const emailList = Array.isArray(response.data) ? response.data : [];
      setEmails(emailList);
      setError("");
      if (!notificationInitialized.current) {
        knownEmailIds.current = new Set(emailList.filter((e) => e?.id).map((e) => e.id));
        notificationInitialized.current = true;
      }
      return emailList;
    } catch (err) {
      console.error("Failed to load emails:", err);
      setError(errorMessage(err, "Failed to load emails."));
      return [];
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  // ---------- LOAD BRIEFING (unchanged API call) ----------
  const loadBriefing = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/emails/briefing`);
      setBriefing(response.data?.briefing || "");
      setBriefingError(false);
    } catch (err) {
      console.error("Failed to load briefing:", err);
      setBriefingError(true);
    }
  }, []);

  // ---------- INITIAL LOAD + AUTO SYNC (unchanged) ----------
  useEffect(() => {
    let mounted = true;
    const initialize = async () => {
      await requestNotificationPermission();
      if (!mounted) return;
      await loadEmails(true);
      if (!mounted) return;
      await loadBriefing();
    };
    initialize();
    const interval = setInterval(async () => {
      if (!mounted) return;
      try {
        await axios.post(`${API}/emails/sync`);
        const response = await axios.get(`${API}/emails/`);
        const emailList = Array.isArray(response.data) ? response.data : [];
        if (!mounted) return;
        notifyNewEmails(emailList);
        setEmails(emailList);
        await loadBriefing();
      } catch (err) {
        console.error("Automatic sync failed:", err);
      }
    }, 5 * 60 * 1000);
    return () => { mounted = false; clearInterval(interval); };
  }, [requestNotificationPermission, loadEmails, loadBriefing, notifyNewEmails]);

  // ---------- MANUAL SYNC (alert -> toast) ----------
  const syncEmails = async () => {
    if (syncing) return;
    setSyncing(true);
    setError("");
    try {
      await axios.post(`${API}/emails/sync`);
      const response = await axios.get(`${API}/emails/`);
      const emailList = Array.isArray(response.data) ? response.data : [];
      notifyNewEmails(emailList);
      setEmails(emailList);
      await loadBriefing();
      toast("Inbox synced");
    } catch (err) {
      console.error("Email sync failed:", err);
      const message = errorMessage(err, "Email sync failed.");
      setError(message);
      toast(message, "err");
    } finally {
      setSyncing(false);
    }
  };

  // ---------- REFRESH BRIEFING (alert -> toast) ----------
  const refreshBriefing = async () => {
    if (briefingLoading) return;
    setBriefingLoading(true);
    try {
      const response = await axios.get(`${API}/emails/briefing`);
      setBriefing(response.data?.briefing || "");
      setBriefingError(false);
      toast("Briefing updated");
    } catch (err) {
      console.error("Failed to generate briefing:", err);
      setBriefingError(true);
      toast(errorMessage(err, "Could not generate the briefing"), "err");
    } finally {
      setBriefingLoading(false);
    }
  };

  // ---------- MARK READ / OPEN / CLOSE (unchanged) ----------
  const markEmailAsRead = async (email) => {
    if (!email?.unread) return;
    try {
      await axios.patch(`${API}/emails/${email.id}/read`);
      setEmails((cur) => cur.map((i) => (i.id === email.id ? { ...i, unread: false } : i)));
      setSelectedEmail((cur) => (cur?.id === email.id ? { ...cur, unread: false } : cur));
    } catch (err) {
      console.error("Failed to mark email as read:", err);
    }
  };
  const openEmail = async (email) => {
    if (!email) return;
    setSelectedEmail(email);
    await markEmailAsRead(email);
  };
  const closeEmail = () => setSelectedEmail(null);

  useEffect(() => {
    if (!selectedEmail) return;
    const onKey = (e) => e.key === "Escape" && setSelectedEmail(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedEmail]);

  // ---------- DEADLINE STATUS (unchanged) ----------
  const getDeadlineStatus = (deadline) => {
    if (!deadline) return "";
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const date = new Date(`${deadline}T00:00:00`);
    if (Number.isNaN(date.getTime())) return "Invalid date";
    const diff = Math.ceil((date - today) / 86400000);
    if (diff < 0) return "Overdue";
    if (diff === 0) return "Due Today";
    if (diff === 1) return "Due Tomorrow";
    return `${diff} days left`;
  };

  // ---------- DERIVED DATA ----------
  const highPriority = useMemo(() => emails.filter((e) => e.priority === "high").length, [emails]);
  const actionEmails = useMemo(() => emails.filter((e) => e.action_required === true), [emails]);
  const unreadCount = useMemo(() => emails.filter((e) => e.unread === true).length, [emails]);
  const deadlineEmails = useMemo(
    () => emails.filter((e) => Boolean(e.deadline)).sort((a, b) => String(a.deadline).localeCompare(String(b.deadline))),
    [emails]
  );
  const categoryCounts = useMemo(() => {
    const counts = {};
    emails.forEach((e) => { const c = e.category || "other"; counts[c] = (counts[c] || 0) + 1; });
    return counts;
  }, [emails]);

  const filteredEmails = useMemo(() => {
    const q = search.toLowerCase().trim();
    return emails.filter((email) => {
      const text = `${email.subject || ""} ${email.sender || ""} ${email.summary || ""} ${email.body || ""} ${email.category || ""} ${email.action_text || ""} ${email.action_type || ""}`.toLowerCase();
      if (q && !text.includes(q)) return false;
      if (filter === "high") return email.priority === "high";
      if (filter === "action") return email.action_required === true;
      if (filter === "unread") return email.unread === true;
      if (filter === "deadlines") return Boolean(email.deadline);
      if (filter !== "all") return email.category === filter;
      return true;
    });
  }, [emails, filter, search]);

  const counts = { all: emails.length, high: highPriority, unread: unreadCount, action: actionEmails.length, deadlines: deadlineEmails.length };
  const setEmailFilter = (v) => { setFilter(v); setMenuOpen(false); };
  const [title, desc] = TITLES[filter] || [cap(filter), `Emails in the ${filter} category`];
  const maxCat = Math.max(1, ...Object.values(categoryCounts));

  const NavBtn = ({ id, icon, label, count }) => (
    <button className="nav" aria-current={filter === id ? "true" : undefined} onClick={() => setEmailFilter(id)}>
      <Icon n={icon} />{label}{count !== undefined && <span className="n">{count}</span>}
    </button>
  );

  // ---------- RENDER ----------
  return (
    <div className="app">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`} aria-label="Main navigation">
        <div className="brand">
          <div className="logo"><Icon n="mail" s={18} /></div>
          <div>Personal AI<small>Email Manager</small></div>
        </div>
        {NAV.map(([id, icon, label]) => <NavBtn key={id} id={id} icon={icon} label={label} count={counts[id]} />)}
        <div className="grp">AI assistant</div>
        {AI_NAV.map(([id, icon, label]) => <NavBtn key={id} id={id} icon={icon} label={label} count={counts[id]} />)}
        <div className="grp">Categories</div>
        {CATEGORIES.map((c) => <NavBtn key={c} id={c} icon="tag" label={cap(c)} count={categoryCounts[c] || 0} />)}
        <div className="sp" />
        <button className="nav" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          <Icon n={theme === "dark" ? "sun" : "moon"} />{theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        {onLogout && (
          <button className="nav" onClick={onLogout}>
            <Icon n="logout" />Log out
          </button>
        )}
      </aside>
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}

      <main className="main">
        <header>
          <button className="ib menu-btn" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Icon n="menu" /></button>
          <div className="ttl"><h1>{title}</h1><p>{desc}</p></div>
          <label className="search">
            <Icon n="search" />
            <input type="search" placeholder="Search emails" aria-label="Search emails" value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
          <button className="btn p" onClick={syncEmails} disabled={syncing}>
            {syncing ? <i className="spin" /> : <Icon n="refresh" />}<span>{syncing ? "Syncing…" : "Sync Gmail"}</span>
          </button>
          <div className="status" title={error || "Connected"}>
            <i className={`dot ${error ? "bad" : ""}`} /><span>{error ? "Offline" : "Gmail connected"}</span>
          </div>
        </header>

        {error && <div className="banner" role="alert"><Icon n="alert" />{error}</div>}

        <section className="card brief" aria-labelledby="bt">
          <div className="bh">
            <div>
              <h2 id="bt"><AIBadge>AI</AIBadge>AI Daily Briefing</h2>
              <p>Your important emails, summarized</p>
            </div>
            <button className="btn" onClick={refreshBriefing} disabled={briefingLoading}>
              {briefingLoading ? <i className="spin" /> : <Icon n="refresh" />}
              <span>{briefingLoading ? "Generating…" : briefing ? "Refresh briefing" : "Generate briefing"}</span>
            </button>
          </div>
          <div aria-live="polite">
            {briefingLoading || (!briefing && !briefingError && loading) ? <Skeleton rows={4} />
              : briefingError && !briefing ? <div className="empty err"><b>Could not generate the briefing</b>The AI service did not respond. Check the backend and try again.</div>
              : briefing ? <BriefingText text={briefing} />
              : <div className="empty"><b>No briefing yet</b>Generate one to see what matters today.</div>}
          </div>
        </section>

        <section className="stats" aria-label="Email overview">
          {[["Total emails", emails.length, "In your inbox", "inbox", "all"],
            ["High priority", highPriority, "Marked by AI", "flag", "high"],
            ["Action required", actionEmails.length, "Waiting on you", "check", "action"],
            ["Unread", unreadCount, "Not opened yet", "mail", "unread"],
            ["Deadlines", deadlineEmails.length, "Dates detected", "clock", "deadlines"]].map(([l, n, d, i, f]) => (
            <button key={l} className="card stat" onClick={() => setEmailFilter(f)} aria-label={`${l}: ${n}`}>
              <span className="t">{l}<Icon n={i} /></span>
              <b>{loading ? "–" : n}</b><small>{d}</small>
              <span className="bar"><i style={{ width: `${emails.length ? Math.round((n / emails.length) * 100) : 0}%` }} /></span>
            </button>
          ))}
        </section>

        <div className="two">
          <section className="card sec">
            <h2><AIBadge /> Upcoming deadlines</h2>
            <p className="sub">Dates found in your emails</p>
            {deadlineEmails.length === 0 ? <div className="empty"><b>No deadlines</b>When an email mentions a due date, it appears here.</div> : (
              <ul className="tl">
                {deadlineEmails.map((email) => {
                  const status = getDeadlineStatus(email.deadline);
                  const cls = status === "Overdue" ? "overdue" : status === "Due Today" ? "today" : "";
                  const d = new Date(`${email.deadline}T00:00:00`);
                  return (
                    <li key={`deadline-${email.id}`}>
                      <button className="tlbtn" onClick={() => openEmail(email)}>
                        <span className="dt">
                          <b>{Number.isNaN(d.getTime()) ? "–" : d.getDate()}</b>
                          <span>{Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short" })}</span>
                        </span>
                        <span className="grow">
                          <span className="s">{email.subject || "No Subject"}</span>
                          <span className="m">{email.sender || "Unknown sender"} · {email.action_text || "Deadline detected"}</span>
                        </span>
                        <span className={`pri ${cls}`}>{status}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="card sec">
            <h2><AIBadge /> Action required</h2>
            <p className="sub">Emails waiting on a reply or decision</p>
            {actionEmails.length === 0 ? <div className="empty"><b>You are all caught up</b>Nothing needs your attention right now.</div> : (
              <div className="act">
                {actionEmails.slice(0, 4).map((email) => (
                  <article className="ac" key={`action-${email.id}`}>
                    <div className="h">
                      <b>{email.sender || "Unknown sender"}</b>
                      <Priority value={email.priority} />
                      <AIBadge>{cap(email.action_type || "Action")}</AIBadge>
                    </div>
                    <div className="s">{email.subject || "No Subject"}</div>
                    <div className="pv">{email.action_text || "This email requires your attention."}</div>
                    <div className="f"><span>{fmtDate(email.date)}</span><button className="btn" onClick={() => openEmail(email)}>Open email</button></div>
                  </article>
                ))}
                {actionEmails.length > 4 && <button className="btn" onClick={() => setEmailFilter("action")}>View all {actionEmails.length}</button>}
              </div>
            )}
          </section>
        </div>

        <section className="card sec">
          <h2>Email analytics</h2>
          <p className="sub">Emails by category</p>
          {Object.keys(categoryCounts).length === 0 ? <div className="empty"><b>No data yet</b>Sync your inbox to see category trends.</div> : (
            <div className="cats">
              {Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
                <button key={c} className="cat" onClick={() => setEmailFilter(c)}>
                  <span>{cap(c)}</span><span className="bar"><i style={{ width: `${(n / maxCat) * 100}%` }} /></span><b>{n}</b>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="card list">
          <div className="lh"><h2>{title}</h2><span className="cnt">{filteredEmails.length} email{filteredEmails.length !== 1 ? "s" : ""}</span></div>
          {loading ? <div className="pad"><Skeleton rows={5} /></div>
            : filteredEmails.length === 0 ? <div className="empty"><b>{search ? "No matches" : "Nothing here yet"}</b>{search ? "Try a different search term." : "Emails in this view will appear here."}</div>
            : filteredEmails.map((email) => (
              <div key={email.id} className={`row ${email.unread ? "un" : ""}`} role="button" tabIndex={0}
                onClick={() => openEmail(email)} onKeyDown={(e) => e.key === "Enter" && openEmail(email)}>
                <span className="from">{email.sender || "Unknown sender"}</span>
                <span className="body">
                  <span className="s">{email.subject || "No Subject"}</span>
                  <span className="pv">{email.summary || "No summary available."}</span>
                </span>
                <span className="meta">
                  {email.action_required && <AIBadge>{cap(email.action_type || "Action")}</AIBadge>}
                  {email.deadline && <span className="chip"><Icon n="clock" s={12} />{fmtDate(email.deadline)}</span>}
                  <span className="chip">{cap(email.category || "other")}</span>
                  <Priority value={email.priority} />
                  <span className="tm">{fmtDate(email.date)}</span>
                </span>
              </div>
            ))}
        </section>

        {selectedEmail && (
          <div className="modal-overlay" onClick={closeEmail}>
            <div className="email-detail" role="dialog" aria-modal="true" aria-label="Email" onClick={(e) => e.stopPropagation()}>
              <button className="ib close" onClick={closeEmail} aria-label="Close email" autoFocus><Icon n="x" /></button>
              <h2>{selectedEmail.subject || "No Subject"}</h2>
              <p className="m"><b>{selectedEmail.sender || "Unknown sender"}</b> · {selectedEmail.date || "Unknown date"}</p>
              <div className="tags">
                <Priority value={selectedEmail.priority} />
                <span className="chip">{cap(selectedEmail.category || "other")}</span>
                {selectedEmail.deadline && <span className="chip"><Icon n="clock" s={12} />{selectedEmail.deadline} · {getDeadlineStatus(selectedEmail.deadline)}</span>}
              </div>
              {selectedEmail.action_required && (
                <div className="aibox"><h3><AIBadge>Action required</AIBadge></h3>
                  <p>{selectedEmail.action_text || "This email requires your attention."}</p>
                  {selectedEmail.action_type && <small>Type: {selectedEmail.action_type}</small>}
                </div>
              )}
              <div className="aibox"><h3><AIBadge>AI summary</AIBadge></h3><p>{selectedEmail.summary || "No AI summary available."}</p></div>
              <div className="email-body">{selectedEmail.body || "No email body available."}</div>
            </div>
          </div>
        )}
      </main>

      <div id="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}><Icon n={t.kind === "err" ? "alert" : "check"} />{t.message}</div>)}
      </div>
    </div>
  );
}

export default App;
