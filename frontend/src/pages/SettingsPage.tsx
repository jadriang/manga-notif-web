import { useEffect, useState } from "react";
import { api, type UserProfile } from "../lib/api";
import { Link } from "react-router-dom";

const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME as string;

export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [linkToken, setLinkToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const data = await api.getProfile();
      setProfile(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLinkTelegram = async () => {
    setError("");
    try {
      const result = await api.generateTelegramLink();
      setLinkToken(result.token);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleUnlinkTelegram = async () => {
    try {
      await api.unlinkTelegram();
      setProfile((p) => (p ? { ...p, telegram_chat_id: null } : p));
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (loading) return <div className="page">Loading...</div>;

  const telegramDeepLink = linkToken
    ? `https://t.me/${BOT_USERNAME}?start=${linkToken}`
    : "";

  return (
    <div className="page">
      <header className="header">
        <h1>
          <Link to="/">← Back</Link> Settings
        </h1>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="settings-section">
        <h2>Account</h2>
        <p>Email: {profile?.email}</p>
      </section>

      <section className="settings-section">
        <h2>Telegram Notifications</h2>

        {profile?.telegram_chat_id ? (
          <div>
            <p className="success">
              ✅ Telegram linked (Chat ID: {profile.telegram_chat_id})
            </p>
            <button className="btn-unsub" onClick={handleUnlinkTelegram}>
              Unlink Telegram
            </button>
          </div>
        ) : (
          <div>
            <p>Link your Telegram to receive chapter notifications.</p>
            {telegramDeepLink ? (
              <div>
                <a
                  href={telegramDeepLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="telegram-link"
                >
                  Open Telegram Bot
                </a>
                <p className="hint">
                  Click the link above, then press "Start" in Telegram.
                  Refresh this page after.
                </p>
              </div>
            ) : (
              <button onClick={handleLinkTelegram}>Link Telegram</button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
