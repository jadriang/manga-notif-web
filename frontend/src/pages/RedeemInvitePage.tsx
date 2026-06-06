import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { api, ApiError } from "../lib/api";

const ERROR_MESSAGES: Record<string, string> = {
  invalid_code: "That invite code isn't valid.",
  code_exhausted: "This invite code has been fully used.",
  already_redeemed: "Your account is already set up — try refreshing.",
  rate_limited: "Too many attempts. Wait a minute and try again.",
};

export default function RedeemInvitePage() {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { signOut } = useClerk();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.redeemInvite(code.trim());
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(ERROR_MESSAGES[err.detail] ?? err.detail);
      } else {
        setError("Something went wrong. Try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>📖 Manga Notifier</h1>
          <p className="subtitle">Enter your invite code to get started</p>
        </div>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Invite code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            autoFocus
          />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={loading || !code.trim()}>
            {loading ? "..." : "Redeem"}
          </button>
        </form>

        <p className="login-toggle">
          Wrong account?{" "}
          <a href="#" onClick={(e) => { e.preventDefault(); signOut(); }}>
            Sign out
          </a>
        </p>
      </div>
    </div>
  );
}
