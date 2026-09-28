import { useEffect, useState, useRef } from "react";
import axios from "axios";
import "./App.css";

const API = "http://127.0.0.1:8000";

function App() {
  const [emails, setEmails] = useState([]);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const knownEmailIds = useRef(new Set());
  const [briefing, setBriefing] = useState("");

  useEffect(() => {
    if ("Notification" in window) {
        Notification.requestPermission();
    }
    const loadData = async () => {
      try {
        const emailsRes = await axios.get(`${API}/emails/`);

        setEmails(emailsRes.data);

        knownEmailIds.current = new Set(
            emailsRes.data.map((email) => email.id)
        );

        const briefingRes = await axios.get(`${API}/emails/briefing`);
        setBriefing(briefingRes.data.briefing);
      } catch (error) {
        console.error("Failed to load dashboard:", error);
      }
    };

    loadData();

    const interval = setInterval(async () => {
      try {
        await axios.post(`${API}/emails/sync`);

        const emailsRes = await axios.get(`${API}/emails/`);
        setEmails(emailsRes.data);

        notifyNewEmails(emailsRes.data);

        const briefingRes = await axios.get(`${API}/emails/briefing`);
        setBriefing(briefingRes.data.briefing);

        console.log("Automatic email sync completed.");
      } catch (error) {
        console.error("Automatic sync failed:", error);
      }
    }, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);
    const syncEmails = async () => {
      setSyncing(true);

      try {
        await axios.post(`${API}/emails/sync`);

        const res = await axios.get(`${API}/emails/`);
        setEmails(res.data);

        alert("Emails synced successfully!");
      } catch (error) {
        console.error(error);
        alert("Email sync failed.");
      }

      setSyncing(false);
    };
    const refreshBriefing = async () => {
        setBriefingLoading(true);

        try {
            const res = await axios.get(`${API}/emails/briefing`);
            setBriefing(res.data.briefing);
        } catch (error) {
          console.error(error);
          alert("Failed to generate briefing.");
        }

        setBriefingLoading(false);
    };
        const notifyNewEmails = (emailList) => {
        if (!("Notification" in window)) {
            return;
        }

        emailList.forEach((email) => {
            if (knownEmailIds.current.has(email.id)) {
                return;
            }

            knownEmailIds.current.add(email.id);

            if (
                email.priority === "high" ||
                email.action_required
            ) {
                if (Notification.permission === "granted") {
                    new Notification("🤖 AI Mail Alert", {
                        body:
                            email.subject ||
                            "New important email requires your attention."
                    });
                }
            }
        });
    };

  const filteredEmails = emails.filter((email) => {
    const text =
      `${email.subject} ${email.sender} ${email.summary}`.toLowerCase();

    const matchesSearch = text.includes(search.toLowerCase());

    const matchesFilter =
      filter === "all" ||
      (filter === "high" && email.priority === "high") ||
      (filter === "action" && email.action_required) ||
      email.category === filter;

    return matchesSearch && matchesFilter;
  });

  const highPriority = emails.filter(
    (email) => email.priority === "high"
  ).length;

  const actionRequired = emails.filter(
    (email) => email.action_required
  ).length;

  const categoryCounts = {};

  emails.forEach((email) => {
    const category = email.category || "other";
    categoryCounts[category] = (categoryCounts[category] || 0) + 1;
  });

  const actionEmails = emails.filter(
  (email) => email.action_required
  );

    const deadlineEmails = emails.filter(
    (email) => email.deadline
  );
    const getDeadlineStatus = (deadline) => {
    if (!deadline) return "";

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const date = new Date(deadline + "T00:00:00");
    const diff =
      Math.ceil((date - today) / (1000 * 60 * 60 * 24));

    if (diff < 0) return "Overdue";
    if (diff === 0) return "Due Today";
    if (diff === 1) return "Due Tomorrow";
    return `${diff} days left`;
  };


  return (
    <div className="app">
      <aside className="sidebar">
        <h2>🤖 AI Mail</h2>

        <button onClick={() => setFilter("all")}>📧 All Emails</button>
        <button onClick={() => setFilter("high")}>🔴 High Priority</button>
        <button onClick={() => setFilter("action")}>⚡ Action Required</button>
        <button onClick={() => setFilter("internship")}>💼 Internships</button>
        <button onClick={() => setFilter("placement")}>🏢 Placements</button>
        <button onClick={() => setFilter("job")}>💻 Jobs</button>
        <button onClick={() => setFilter("education")}>🎓 Education</button>
        <button onClick={() => setFilter("finance")}>💰 Finance</button>
      </aside>

      <main className="main">
        <header>
          <div>
            <h1>Personal AI Email Manager</h1>
            <p>AI-powered email organization</p>
          </div>
          <button
            className="sync-btn"
            onClick={syncEmails}
            disabled={syncing}
          >
            {syncing ? "⏳ Syncing..." : "🔄 Sync Gmail"}
          </button>

          <input
            type="text"
            placeholder="🔎 Search emails..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </header>

        <section className="briefing-section">

            <div className="briefing-header">
                <div>
                    <h2>🤖 AI Daily Briefing</h2>
                    <span>Powered by Gemini</span>
                </div>

                <button
                    className="refresh-btn"
                    onClick={refreshBriefing}
                    disabled={briefingLoading}
                >
                    {briefingLoading ? "⏳ Generating..." : "🔄 Refresh Briefing"}
                </button>
            </div>

            <div className="briefing-card">
                {briefing ? (
                    <div className="briefing-text">
                        {briefing}
                    </div>
                ) : (
                    <p>Generating your daily briefing...</p>
                )}
            </div>

        </section>

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
        </section>

        <section className="deadline-section">
          <h2>📅 Upcoming Deadlines</h2>

          {deadlineEmails.length === 0 ? (
            <p className="empty">No deadlines found.</p>
          ) : (
            deadlineEmails.map((email) => (
              <div
                className="deadline-card"
                key={`deadline-${email.id}`}
                onClick={() => setSelectedEmail(email)}
              >
                <div>
                  <h3>{email.subject || "No Subject"}</h3>
                  <p>{email.action_text}</p>
                </div>

                <div className="deadline-info">
                  <strong>{email.deadline}</strong>

                  <span
                    className={
                      getDeadlineStatus(email.deadline) === "Overdue"
                        ? "deadline-overdue"
                        : getDeadlineStatus(email.deadline) === "Due Today"
                        ? "deadline-today"
                        : "deadline-upcoming"
                    }
                  >
                    {getDeadlineStatus(email.deadline)}
                  </span>
                </div>
              </div>
            ))
          )}
        </section>

        <section className="analytics-section">
          <h2>📊 Email Analytics</h2>

          <div className="analytics-grid">
            {Object.entries(categoryCounts).map(([category, count]) => (
              <div className="analytics-card" key={category}>
                <h3>{count}</h3>
                <p>{category}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="action-section">
          <h2>⚡ Action Required</h2>

          {actionEmails.length === 0 ? (
            <p className="empty">No actions required.</p>
          ) : (
            actionEmails.map((email) => (
              <div
                className="action-card"
                key={`action-${email.id}`}
                onClick={() => setSelectedEmail(email)}
              >
                <div>
                  <h3>{email.subject || "No Subject"}</h3>

                  <p>
                    {email.action_text || "Action required"}
                  </p>
                </div>

                <span className="action-type">
                  {email.action_type || "action"}
                </span>
              </div>
            ))
          )}
        </section>

        <section className="emails">
          {filteredEmails.map((email) => (
            <div
              className={`email-card ${
                email.unread ? "unread" : ""
              }`}
              key={email.id}
              onClick={async () => {
                console.log("CLICKED EMAIL:", email);

                setSelectedEmail(email);

                if (email.unread) {
                  try {
                    await axios.patch(`${API}/emails/${email.id}/read`);

                    setEmails((currentEmails) =>
                      currentEmails.map((item) =>
                        item.id === email.id
                          ? { ...item, unread: false }
                          : item
                      )
                    );
                  } catch (error) {
                    console.error("Failed to mark email as read:", error);
                  }
                }
              }}
            >
              <div className="email-top">
                <h3>
                  {email.unread && (
                    <span className="unread-dot">●</span>
                  )}
                  {email.subject || "No Subject"}
                </h3>

                <span className={`priority ${email.priority}`}>
                  {email.priority || "unknown"}
                </span>
              </div>

              <p className="sender">{email.sender}</p>

              <div className="tags">
                <span>{email.category || "other"}</span>

                {email.action_required && (
                  <span className="action-tag">
                    ⚡ {email.action_type || "Action Required"}
                  </span>
                )}

                {email.action_required && email.action_text && (
                  <p className="action-text">
                    {email.action_text}
                  </p>
                )}
              </div>

              <p className="summary">
                {email.summary || "No summary available."}
              </p>
            </div>
          ))}

          {filteredEmails.length === 0 && (
            <p className="empty">No emails found.</p>
          )}
        </section>

        {selectedEmail && (
          <div
            className="modal-overlay"
            onClick={() => setSelectedEmail(null)}
          >
            <div
              className="email-detail"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                className="close-btn"
                onClick={() => setSelectedEmail(null)}
              >
                ✕
              </button>

              <h2>{selectedEmail.subject || "No Subject"}</h2>

              <p className="sender">
                <strong>From:</strong> {selectedEmail.sender}
              </p>

              <p className="date">
                <strong>Date:</strong> {selectedEmail.date}
              </p>

              <div className="detail-tags">
                <span className={`priority ${selectedEmail.priority}`}>
                  {selectedEmail.priority}
                </span>

                <span>{selectedEmail.category}</span>

                {selectedEmail.action_required && (
                  <span className="action-tag">
                    ⚡ Action Required
                  </span>
                )}
              </div>

              <div className="ai-summary">
                <h3>🤖 AI Summary</h3>
                <p>{selectedEmail.summary}</p>
              </div>

              <hr />

              <h3>Email</h3>

              <div className="email-body">
                {selectedEmail.body || "No email body available."}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;