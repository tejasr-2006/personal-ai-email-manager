import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

const API = import.meta.env.VITE_API_URL;

function App() {
  // =========================================================
  // STATE
  // =========================================================

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

  // =========================================================
  // NOTIFICATIONS
  // =========================================================

  const requestNotificationPermission = useCallback(async () => {
    if (!("Notification" in window)) return;

    if (Notification.permission === "default") {
      try {
        await Notification.requestPermission();
      } catch (err) {
        console.error("Notification permission failed:", err);
      }
    }
  }, []);

  const notifyNewEmails = useCallback((newEmails) => {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;

    newEmails.forEach((email) => {
      if (!email?.id) return;

      // Prevent duplicate notifications
      if (knownEmailIds.current.has(email.id)) {
        return;
      }

      const isImportant =
        email.priority === "high" ||
        email.action_required === true ||
        email.category === "internship" ||
        email.category === "placement" ||
        email.category === "job" ||
        email.category === "recruitment";

      // Remember this email
      knownEmailIds.current.add(email.id);

      if (!isImportant) return;

      new Notification("🤖 Important Email", {
        body:
          `${email.subject || "New important email"}\n` +
          `${email.summary || "Requires your attention."}`,
        icon: "/favicon.ico",
      });
    });
  }, []);

  // =========================================================
  // LOAD EMAILS
  // =========================================================

  const loadEmails = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setLoading(true);
    }

    try {
      const response = await axios.get(`${API}/emails/`);

      const emailList = Array.isArray(response.data)
        ? response.data
        : [];

      setEmails(emailList);
      setError("");

      // First load should establish the baseline.
      if (!notificationInitialized.current) {
        knownEmailIds.current = new Set(
          emailList
            .filter((email) => email?.id)
            .map((email) => email.id)
        );

        notificationInitialized.current = true;
      }

      return emailList;
    } catch (err) {
      console.error("Failed to load emails:", err);
      setError(
        "Failed to load emails. Make sure the backend is running."
      );
      return [];
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }, []);

  // =========================================================
  // LOAD AI BRIEFING
  // =========================================================

  const loadBriefing = useCallback(async () => {
    try {
      const response = await axios.get(
        `${API}/emails/briefing`
      );

      setBriefing(response.data?.briefing || "");
    } catch (err) {
      console.error("Failed to load briefing:", err);
    }
  }, []);

  // =========================================================
  // INITIAL LOAD + AUTO SYNC
  // =========================================================

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

        const emailList = Array.isArray(response.data)
          ? response.data
          : [];

        if (!mounted) return;

        notifyNewEmails(emailList);
        setEmails(emailList);
        await loadBriefing();

        console.log("Automatic email sync completed.");
      } catch (err) {
        console.error("Automatic sync failed:", err);
      }
    }, 5 * 60 * 1000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [
    requestNotificationPermission,
    loadEmails,
    loadBriefing,
    notifyNewEmails,
  ]);

  // =========================================================
  // MANUAL EMAIL SYNC
  // =========================================================

  const syncEmails = async () => {
    if (syncing) return;

    setSyncing(true);
    setError("");

    try {
      await axios.post(`${API}/emails/sync`);

      const response = await axios.get(`${API}/emails/`);

      const emailList = Array.isArray(response.data)
        ? response.data
        : [];

      notifyNewEmails(emailList);

      setEmails(emailList);

      await loadBriefing();

      alert("Emails synced successfully!");
    } catch (err) {
      console.error("Email sync failed:", err);

      setError(
        "Email sync failed. Check whether the backend is running."
      );

      alert("Email sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  // =========================================================
  // REFRESH AI BRIEFING
  // =========================================================

  const refreshBriefing = async () => {
    if (briefingLoading) return;

    setBriefingLoading(true);

    try {
      const response = await axios.get(
        `${API}/emails/briefing`
      );

      setBriefing(response.data?.briefing || "");
    } catch (err) {
      console.error("Failed to generate briefing:", err);
      alert("Failed to generate briefing.");
    } finally {
      setBriefingLoading(false);
    }
  };

  // =========================================================
  // MARK EMAIL AS READ
  // =========================================================

  const markEmailAsRead = async (email) => {
    if (!email?.unread) return;

    try {
      await axios.patch(
        `${API}/emails/${email.id}/read`
      );

      setEmails((currentEmails) =>
        currentEmails.map((item) =>
          item.id === email.id
            ? { ...item, unread: false }
            : item
        )
      );

      setSelectedEmail((currentEmail) =>
        currentEmail?.id === email.id
          ? { ...currentEmail, unread: false }
          : currentEmail
      );
    } catch (err) {
      console.error(
        "Failed to mark email as read:",
        err
      );
    }
  };

  // =========================================================
  // OPEN EMAIL
  // =========================================================

  const openEmail = async (email) => {
    if (!email) return;

    setSelectedEmail(email);

    await markEmailAsRead(email);
  };

  // =========================================================
  // CLOSE EMAIL
  // =========================================================

  const closeEmail = () => {
    setSelectedEmail(null);
  };

  // =========================================================
  // DEADLINE STATUS
  // =========================================================

  const getDeadlineStatus = (deadline) => {
    if (!deadline) return "";

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const date = new Date(`${deadline}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
      return "Invalid date";
    }

    const diff = Math.ceil(
      (date - today) /
        (1000 * 60 * 60 * 24)
    );

    if (diff < 0) return "Overdue";
    if (diff === 0) return "Due Today";
    if (diff === 1) return "Due Tomorrow";

    return `${diff} days left`;
  };

  // =========================================================
  // STATISTICS
  // IMPORTANT:
  // All derived arrays are created BEFORE JSX.
  // This prevents the actionEmails initialization error.
  // =========================================================

  const highPriorityEmails = useMemo(
    () =>
      emails.filter(
        (email) => email.priority === "high"
      ),
    [emails]
  );

  const actionEmails = useMemo(
    () =>
      emails.filter(
        (email) => email.action_required === true
      ),
    [emails]
  );

  const unreadEmails = useMemo(
    () =>
      emails.filter(
        (email) => email.unread === true
      ),
    [emails]
  );

  const deadlineEmails = useMemo(
    () =>
      emails.filter(
        (email) => Boolean(email.deadline)
      ),
    [emails]
  );

  const highPriority = highPriorityEmails.length;
  const actionRequired = actionEmails.length;
  const unreadCount = unreadEmails.length;

  // =========================================================
  // CATEGORY COUNTS
  // =========================================================

  const categoryCounts = useMemo(() => {
    const counts = {};

    emails.forEach((email) => {
      const category = email.category || "other";

      counts[category] =
        (counts[category] || 0) + 1;
    });

    return counts;
  }, [emails]);

  // =========================================================
  // FILTERED EMAILS
  // =========================================================

  const filteredEmails = useMemo(() => {
    const searchText = search
      .toLowerCase()
      .trim();

    return emails.filter((email) => {
      const text = `
        ${email.subject || ""}
        ${email.sender || ""}
        ${email.summary || ""}
        ${email.body || ""}
        ${email.category || ""}
        ${email.action_text || ""}
        ${email.action_type || ""}
      `.toLowerCase();

      const matchesSearch =
        !searchText ||
        text.includes(searchText);

      let matchesFilter = true;

      if (filter === "high") {
        matchesFilter =
          email.priority === "high";
      } else if (filter === "action") {
        matchesFilter =
          email.action_required === true;
      } else if (filter !== "all") {
        matchesFilter =
          email.category === filter;
      }

      return matchesSearch && matchesFilter;
    });
  }, [emails, filter, search]);

  // =========================================================
  // FILTER BUTTON
  // =========================================================

  const setEmailFilter = (value) => {
    setFilter(value);
  };

  // =========================================================
  // RENDER
  // =========================================================

  return (
    <div className="app">

      {/* =====================================================
          SIDEBAR
      ====================================================== */}

      <aside className="sidebar">

        <h2>🤖 AI Mail</h2>

        <button
          className={filter === "all" ? "active" : ""}
          onClick={() => setEmailFilter("all")}
        >
          📧 All Emails
        </button>

        <button
          className={filter === "high" ? "active" : ""}
          onClick={() => setEmailFilter("high")}
        >
          🔴 High Priority
        </button>

        <button
          className={
            filter === "action" ? "active" : ""
          }
          onClick={() => setEmailFilter("action")}
        >
          ⚡ Action Required
        </button>

        <button
          className={
            filter === "internship"
              ? "active"
              : ""
          }
          onClick={() =>
            setEmailFilter("internship")
          }
        >
          💼 Internships
        </button>

        <button
          className={
            filter === "placement"
              ? "active"
              : ""
          }
          onClick={() =>
            setEmailFilter("placement")
          }
        >
          🏢 Placements
        </button>

        <button
          className={
            filter === "job" ? "active" : ""
          }
          onClick={() => setEmailFilter("job")}
        >
          💻 Jobs
        </button>

        <button
          className={
            filter === "recruitment"
              ? "active"
              : ""
          }
          onClick={() =>
            setEmailFilter("recruitment")
          }
        >
          🎯 Recruitment
        </button>

        <button
          className={
            filter === "education"
              ? "active"
              : ""
          }
          onClick={() =>
            setEmailFilter("education")
          }
        >
          🎓 Education
        </button>

        <button
          className={
            filter === "finance"
              ? "active"
              : ""
          }
          onClick={() =>
            setEmailFilter("finance")
          }
        >
          💰 Finance
        </button>

        <button
          className={
            filter === "promotion"
              ? "active"
              : ""
          }
          onClick={() =>
            setEmailFilter("promotion")
          }
        >
          🛍️ Promotions
        </button>

      </aside>

      {/* =====================================================
          MAIN CONTENT
      ====================================================== */}

      <main className="main">

        {/* HEADER */}

        <header>

          <div>
            <h1>
              Personal AI Email Manager
            </h1>

            <p>
              AI-powered email organization
            </p>
          </div>

          <button
            className="sync-btn"
            onClick={syncEmails}
            disabled={syncing}
          >
            {syncing
              ? "⏳ Syncing..."
              : "🔄 Sync Gmail"}
          </button>

          <input
            type="text"
            placeholder="🔎 Search emails..."
            value={search}
            onChange={(event) =>
              setSearch(event.target.value)
            }
          />

        </header>

        {/* ERROR */}

        {error && (
          <div className="error-message">
            ⚠️ {error}
          </div>
        )}

        {/* =====================================================
            AI DAILY BRIEFING
        ====================================================== */}

        <section className="briefing-section">

          <div className="briefing-header">

            <div>
              <h2>
                🤖 AI Daily Briefing
              </h2>

              <span>
                Powered by Gemini
              </span>
            </div>

            <button
              className="refresh-btn"
              onClick={refreshBriefing}
              disabled={briefingLoading}
            >
              {briefingLoading
                ? "⏳ Generating..."
                : "🔄 Refresh Briefing"}
            </button>

          </div>

          <div className="briefing-card">

            {briefing ? (
              <div className="briefing-text">
                {briefing}
              </div>
            ) : (
              <p>
                Generating your daily briefing...
              </p>
            )}

          </div>

        </section>

        {/* =====================================================
            STATISTICS
        ====================================================== */}

        <section className="stats">

          <div className="stat-card">
            <h3>{emails.length}</h3>
            <p>Total Emails</p>
          </div>

          <div className="stat-card high">
            <h3>{highPriority}</h3>
            <p>High Priority</p>
          </div>

          <div className="stat-card action">
            <h3>{actionRequired}</h3>
            <p>Action Required</p>
          </div>

          <div className="stat-card">
            <h3>{unreadCount}</h3>
            <p>Unread</p>
          </div>

          <div className="stat-card">
            <h3>{deadlineEmails.length}</h3>
            <p>Deadlines</p>
          </div>

        </section>

        {/* =====================================================
            DEADLINES
        ====================================================== */}

        <section className="deadline-section">

          <h2>
            📅 Upcoming Deadlines
          </h2>

          {deadlineEmails.length === 0 ? (

            <p className="empty">
              No deadlines found.
            </p>

          ) : (

            deadlineEmails.map((email) => {

              const deadlineStatus =
                getDeadlineStatus(
                  email.deadline
                );

              let statusClass =
                "deadline-upcoming";

              if (
                deadlineStatus === "Overdue"
              ) {
                statusClass =
                  "deadline-overdue";
              } else if (
                deadlineStatus === "Due Today"
              ) {
                statusClass =
                  "deadline-today";
              }

              return (
                <div
                  className="deadline-card"
                  key={`deadline-${email.id}`}
                  onClick={() =>
                    openEmail(email)
                  }
                >

                  <div>

                    <h3>
                      {email.subject ||
                        "No Subject"}
                    </h3>

                    <p>
                      {email.action_text ||
                        "Deadline detected"}
                    </p>

                  </div>

                  <div className="deadline-info">

                    <strong>
                      {email.deadline}
                    </strong>

                    <span
                      className={statusClass}
                    >
                      {deadlineStatus}
                    </span>

                  </div>

                </div>
              );
            })

          )}

        </section>

        {/* =====================================================
            ANALYTICS
        ====================================================== */}

        <section className="analytics-section">

          <h2>
            📊 Email Analytics
          </h2>

          {Object.keys(categoryCounts).length ===
          0 ? (

            <p className="empty">
              No analytics available.
            </p>

          ) : (

            <div className="analytics-grid">

              {Object.entries(
                categoryCounts
              ).map(([category, count]) => (

                <div
                  className="analytics-card"
                  key={category}
                >

                  <h3>{count}</h3>

                  <p>{category}</p>

                </div>

              ))}

            </div>

          )}

        </section>

        {/* =====================================================
            ACTION REQUIRED
        ====================================================== */}

        <section className="action-section">

          <h2>
            ⚡ Action Required
          </h2>

          {actionEmails.length === 0 ? (

            <p className="empty">
              No actions required 🎉
            </p>

          ) : (

            actionEmails.map((email) => (

              <div
                className="action-card"
                key={`action-${email.id}`}
                onClick={() =>
                  openEmail(email)
                }
              >

                <div>

                  <h3>
                    {email.subject ||
                      "No Subject"}
                  </h3>

                  <p className="sender">
                    {email.sender ||
                      "Unknown sender"}
                  </p>

                  <p>
                    {email.action_text ||
                      "This email requires your attention."}
                  </p>

                </div>

                <span className="action-type">
                  {email.action_type ||
                    "Action"}
                </span>

              </div>

            ))

          )}

        </section>

        {/* =====================================================
            EMAIL LIST
        ====================================================== */}

        <section className="emails">

          <div className="section-header">

            <h2>
              📬 Emails
            </h2>

            <span>
              {filteredEmails.length} email
              {filteredEmails.length !== 1
                ? "s"
                : ""}
            </span>

          </div>

          {loading ? (

            <p className="empty">
              ⏳ Loading emails...
            </p>

          ) : filteredEmails.length === 0 ? (

            <p className="empty">
              No emails found.
            </p>

          ) : (

            filteredEmails.map((email) => (

              <div
                className={`email-card ${
                  email.unread ? "unread" : ""
                }`}
                key={email.id}
                onClick={() =>
                  openEmail(email)
                }
              >

                <div className="email-top">

                  <h3>

                    {email.unread && (
                      <span className="unread-dot">
                        ●
                      </span>
                    )}

                    {email.subject ||
                      "No Subject"}

                  </h3>

                  <span
                    className={`priority ${
                      email.priority ||
                      "unknown"
                    }`}
                  >
                    {email.priority ||
                      "unknown"}
                  </span>

                </div>

                <p className="sender">
                  {email.sender ||
                    "Unknown sender"}
                </p>

                <div className="tags">

                  <span>
                    {email.category ||
                      "other"}
                  </span>

                  {email.action_required && (
                    <span className="action-tag">
                      ⚡{" "}
                      {email.action_type ||
                        "Action Required"}
                    </span>
                  )}

                  {email.deadline && (
                    <span className="action-tag">
                      📅 {email.deadline}
                    </span>
                  )}

                </div>

                {email.action_required &&
                  email.action_text && (
                    <p className="action-text">
                      {email.action_text}
                    </p>
                  )}

                <p className="summary">
                  {email.summary ||
                    "No summary available."}
                </p>

              </div>

            ))

          )}

        </section>

        {/* =====================================================
            EMAIL DETAIL MODAL
        ====================================================== */}

        {selectedEmail && (

          <div
            className="modal-overlay"
            onClick={closeEmail}
          >

            <div
              className="email-detail"
              onClick={(event) =>
                event.stopPropagation()
              }
            >

              <button
                className="close-btn"
                onClick={closeEmail}
                aria-label="Close email"
              >
                ✕
              </button>

              <h2>
                {selectedEmail.subject ||
                  "No Subject"}
              </h2>

              <p className="sender">
                <strong>From:</strong>{" "}
                {selectedEmail.sender ||
                  "Unknown sender"}
              </p>

              <p className="date">
                <strong>Date:</strong>{" "}
                {selectedEmail.date ||
                  "Unknown date"}
              </p>

              {/* TAGS */}

              <div className="detail-tags">

                <span
                  className={`priority ${
                    selectedEmail.priority ||
                    "unknown"
                  }`}
                >
                  {selectedEmail.priority ||
                    "unknown"}
                </span>

                <span>
                  {selectedEmail.category ||
                    "other"}
                </span>

                {selectedEmail.action_required && (
                  <span className="action-tag">
                    ⚡ Action Required
                  </span>
                )}

                {selectedEmail.deadline && (
                  <span className="action-tag">
                    📅{" "}
                    {selectedEmail.deadline}
                  </span>
                )}

              </div>

              {/* ACTION */}

              {selectedEmail.action_required && (
                <div className="ai-summary">

                  <h3>
                    ⚡ Required Action
                  </h3>

                  <p>
                    {selectedEmail.action_text ||
                      "This email requires your attention."}
                  </p>

                  {selectedEmail.action_type && (
                    <small>
                      Type:{" "}
                      {selectedEmail.action_type}
                    </small>
                  )}

                </div>
              )}

              {/* AI SUMMARY */}

              <div className="ai-summary">

                <h3>
                  🤖 AI Summary
                </h3>

                <p>
                  {selectedEmail.summary ||
                    "No AI summary available."}
                </p>

              </div>

              <hr />

              <h3>Email</h3>

              <div className="email-body">
                {selectedEmail.body ||
                  "No email body available."}
              </div>

            </div>

          </div>

        )}

      </main>

    </div>
  );
}

export default App;