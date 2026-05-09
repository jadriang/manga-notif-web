import { useState } from "react";
import { supabase } from "../lib/supabase";

const API_URL = import.meta.env.VITE_API_URL as string;

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [signedUp, setSignedUp] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (isSignUp) {
      try {
        const resp = await fetch(
          `${API_URL}/api/auth/check-email?email=${encodeURIComponent(email)}`
        );
        const data = await resp.json();
        if (!data.allowed) {
          setError("You're not on the access list.");
          setLoading(false);
          return;
        }
      } catch {
        setError("Could not verify email. Please try again.");
        setLoading(false);
        return;
      }
    }

    const { error } = isSignUp
      ? await supabase.auth.signUp({ email, password })
      : await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError(error.message);
    } else if (isSignUp) {
      setSignedUp(true);
    }
    setLoading(false);
  };

  if (signedUp) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <h1>📖 Manga Notifier</h1>
          </div>
          <div className="verify-email">
            <p className="verify-icon">📬</p>
            <h2>Check your email</h2>
            <p>We sent a verification link to <strong>{email}</strong>. Click it to activate your account, then sign in.</p>
          </div>
          <p className="login-toggle">
            Already verified?{" "}
            <a href="#" onClick={() => { setSignedUp(false); setIsSignUp(false); }}>
              Sign in
            </a>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>📖 Manga Notifier</h1>
          <p className="subtitle">Track new chapters automatically</p>
        </div>

        <form onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={loading}>
            {loading ? "..." : isSignUp ? "Create Account" : "Sign In"}
          </button>
        </form>

        <p className="login-toggle">
          {isSignUp ? "Already have an account?" : "Don't have an account?"}{" "}
          <a href="#" onClick={() => { setIsSignUp(!isSignUp); setError(""); }}>
            {isSignUp ? "Sign in" : "Sign up"}
          </a>
        </p>
      </div>
    </div>
  );
}
