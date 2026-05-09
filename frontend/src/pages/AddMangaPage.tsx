import { useState } from "react";
import { api } from "../lib/api";
import { Link, useNavigate } from "react-router-dom";

export default function AddMangaPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const result = await api.createManga(url, title || undefined);
      if (result.already_existed) {
        setSuccess(`Subscribed to "${result.title}" (already being tracked)`);
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
        <h1>
          <Link to="/">← Back</Link> Add Manga
        </h1>
      </header>

      <div className="add-form-container">
        <p className="error">Adding manga is temporarily disabled. Check back later.</p>
        <form onSubmit={handleSubmit} className="add-form" style={{ opacity: 0.5, pointerEvents: "none" }}>
          <label>
            Manga URL
            <input
              type="url"
              placeholder="https://asurascans.com/comics/nano-machine-75e30c62"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </label>
          <p className="hint">
            Paste a manga page URL from AsuraScans or DemonicScans
          </p>

          <label>
            Title (optional — auto-detected from URL)
            <input
              type="text"
              placeholder="Nano Machine"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>

          {error && <p className="error">{error}</p>}
          {success && <p className="success">{success}</p>}

          <button type="submit" disabled={loading}>
            {loading ? "Adding..." : "Add Manga"}
          </button>
        </form>
      </div>
    </div>
  );
}
