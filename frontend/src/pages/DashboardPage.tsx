import { useEffect, useState } from "react";
import { api, type Manga } from "../lib/api";
import { useClerk } from "@clerk/clerk-react";
import { Link } from "react-router-dom";

type FilterTab = "all" | "subscribed";

export default function DashboardPage() {
  const { signOut } = useClerk();
  const [manga, setManga] = useState<Manga[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterTab>("all");

  useEffect(() => {
    loadManga();
  }, []);

  const loadManga = async () => {
    try {
      const data = await api.listManga();
      setManga(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSub = async (mangaId: string) => {
    try {
      await api.toggleSubscription(mangaId);
      setManga((prev) =>
        prev.map((m) =>
          m.id === mangaId ? { ...m, subscribed: !m.subscribed } : m
        )
      );
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (loading) {
    return (
      <div className="page loading-page">
        <div className="loader"></div>
      </div>
    );
  }

  const filtered = filter === "subscribed" ? manga.filter((m) => m.subscribed) : manga;
  const subscribedCount = manga.filter((m) => m.subscribed).length;

  return (
    <div className="page">
      <header className="header">
        <div className="header-brand">
          <span className="brand-icon">📖</span>
          <h1>Manga Notifier</h1>
        </div>
        <nav>
          <span className="btn-add" style={{ opacity: 0.4, cursor: "not-allowed" }}>+ Add Manga</span>
          <Link to="/settings">Settings</Link>
          <button className="signout-btn" onClick={() => signOut()}>Sign Out</button>
        </nav>
      </header>

      {error && <p className="error">{error}</p>}

      <div className="dashboard-toolbar">
        <div className="filter-tabs">
          <button
            className={`filter-tab ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            All <span className="tab-count">{manga.length}</span>
          </button>
          <button
            className={`filter-tab ${filter === "subscribed" ? "active" : ""}`}
            onClick={() => setFilter("subscribed")}
          >
            Subscribed <span className="tab-count">{subscribedCount}</span>
          </button>
        </div>
      </div>

      <div className="manga-grid">
        {filtered.map((m) => (
          <div key={m.id} className={`manga-card ${m.subscribed ? "subscribed" : ""}`}>
            <div className="card-cover">
              {m.cover_url ? (
                <img src={m.cover_url} alt={m.title} className="cover" />
              ) : (
                <div className="cover-placeholder">📖</div>
              )}
              {m.subscribed && <span className="subscribed-badge">✓</span>}
            </div>
            <div className="manga-info">
              <h3 title={m.title}>{m.title}</h3>
              <div className="sites">
                {m.asura_slug && <span className="site-tag site-asura">AsuraScans</span>}
                {m.demonic_slug && <span className="site-tag site-demonic">DemonicScans</span>}
              </div>
              <div className="chapters">
                {Object.entries(m.latest_chapters).map(([site, ch]) => (
                  <span key={site} className="chapter-badge">
                    Ch.{ch}
                  </span>
                ))}
              </div>
              <button
                className={m.subscribed ? "btn-unsub" : "btn-sub"}
                onClick={() => toggleSub(m.id)}
              >
                {m.subscribed ? "Unsubscribe" : "Subscribe"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="empty-state">
          {filter === "subscribed" ? (
            <>
              <p>No subscriptions yet.</p>
              <button className="filter-tab" onClick={() => setFilter("all")}>
                View all manga
              </button>
            </>
          ) : (
            <p>No manga tracked yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
