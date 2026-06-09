import { SignIn, SignUp } from "@clerk/clerk-react";
import { useState } from "react";

export default function LoginPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  return (
    <div className="login-page login-page--auth">
      <div className="login-brand">
        <h1>📖 Manga Notifier</h1>
        <p className="subtitle">Track new chapters automatically</p>
      </div>

      {mode === "signin" ? (
        <SignIn routing="hash" signUpUrl="#" />
      ) : (
        <SignUp routing="hash" signInUrl="#" />
      )}

      <p className="login-toggle">
        {mode === "signin" ? "Don't have an account?" : "Already have an account?"}{" "}
        <a href="#" onClick={(e) => { e.preventDefault(); setMode(mode === "signin" ? "signup" : "signin"); }}>
          {mode === "signin" ? "Sign up" : "Sign in"}
        </a>
      </p>
    </div>
  );
}
