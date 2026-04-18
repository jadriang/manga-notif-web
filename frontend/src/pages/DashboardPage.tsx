import { useEffect, useState } from "react";
import { api, type Manga } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { Link } from "react-router-dom";

export default function DashboardPage() {
  const { signOut } = useAuth();
  const [manga, setManga] = useState<Manga[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  if (loading) return <div className="page">Loading...</div>;

  return (
    <div className="page">
      <header className="header">
        <h1>📖 Manga Notifier</h1>
        <nav>
          <Link to="/add">+ Add Manga</Link>
          <Link to="/settings">Settings</Link>
          <a href="#" onClick={signOut}>
            Sign Out
          </a>
        </nav>
      </header>

      {error && <p className="error">{error}</p>}

      <h2>All Manga</h2>
      <div className="manga-grid">
        {manga.map((m) => (
          <div key={m.id} className={`manga-card ${m.subscribed ? "subscribed" : ""}`}>
            {m.cover_url && (
              <img src={m.cover_url} alt={m.title} className="cover" />
            )}
            <div className="manga-info">
              <h3>{m.title}</h3>
              <div className="chapters">
                {Object.entries(m.latest_chapters).map(([site, ch]) => (
                  <span key={site} className="chapter-badge">
                    {site}: Ch.{ch}
                  </span>
                ))}
              </div>
              <div className="sites">
                {m.asura_slug && <span className="site-tag">AsuraScans</span>}
                {m.demonic_slug && (
                  <span className="site-tag">DemonicScans</span>
                )}
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

      {manga.length === 0 && (
        <p className="empty">
          No manga tracked yet. <Link to="/add">Add one!</Link>
        </p>
      )}
    </div>
  );
}
