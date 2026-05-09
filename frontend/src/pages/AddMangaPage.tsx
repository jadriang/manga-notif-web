import { useState } from "react";
import { api } from "../lib/api";
import { Link } from "react-router-dom";

type DetectedSite = "asura" | "demonic" | null;

function detectSite(url: string): DetectedSite {
  if (!url) return null;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    if (hostname.includes("asura")) return "asura";
    if (hostname.includes("demonic")) return "demonic";
  } catch {
    const lower = url.toLowerCase();
    if (lower.includes("asura")) return "asura";
    if (lower.includes("demonic")) return "demonic";
  }
  return null;
}

export default function AddMangaPage() {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const detectedSite = detectSite(url);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const result = await api.createManga(url, title || undefined);
      if (result.already_existed) {
        setSuccess(`Subscribed to "${result.title}" (already tracked)`);
      } else {
        setSuccess(`Added "${result.title}" and subscribed!`);
      }
      setUrl("");
      setTitle("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <header className="header">
        <div className="header-left">
          <Link to="/" className="back-link">← Back</Link>
          <h1>Add Manga</h1>
        </div>
      </header>

      <div className="add-form-container">
        <p className="error">Adding manga is temporarily disabled. Check back later.</p>
        <div className="add-form-card" style={{ opacity: 0.5, pointerEvents: "none" }}>
          <p className="add-form-desc">
            Paste a manga page URL from AsuraScans or DemonicScans. The title and latest chapter will be fetched automatically.
          </p>

          <form onSubmit={handleSubmit} className="add-form">
            <div className="input-group">
              <label htmlFor="url-input">Manga Page URL</label>
              <div className="url-input-wrapper">
                <input
                  id="url-input"
                  type="url"
                  placeholder="https://asurascans.com/comics/..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  required
                />
                {detectedSite && (
                  <span className={`url-site-badge site-${detectedSite}`}>
                    {detectedSite === "asura" ? "AsuraScans" : "DemonicScans"}
                  </span>
                )}
              </div>
              <div className="url-examples">
                <span className="examples-label">Try:</span>
                <button
                  type="button"
                  className="example-btn"
                  onClick={() => setUrl("https://asurascans.com/comics/nano-machine-75e30c62")}
                >
                  AsuraScans
                </button>
                <button
                  type="button"
                  className="example-btn"
                  onClick={() => setUrl("https://demonicscans.org/manga/nano-machine")}
                >
                  DemonicScans
                </button>
              </div>
            </div>

            <div className="input-group">
              <label htmlFor="title-input">
                Title
                <span className="optional-label">optional — auto-detected</span>
              </label>
              <input
                id="title-input"
                type="text"
                placeholder="Nano Machine"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            {error && <p className="error">{error}</p>}
            {success && <p className="success">{success}</p>}

            <button type="submit" className="submit-btn" disabled={loading}>
              {loading ? "Adding..." : "Add & Subscribe"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
