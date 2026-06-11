import { SignIn, SignUp } from "@clerk/clerk-react";
import { useState } from "react";

// Hide Clerk's built-in "Sign up / Sign in" footer link — it redirects to the
// hosted account portal, which is inconsistent with the inline toggle below.
// We drive the switch ourselves via the toggle so it stays in-app.
const hideFooterAction = { elements: { footerAction: { display: "none" } } } as const;

export default function LoginPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  return (
    <div className="login-page login-page--auth">
      <div className="login-brand">
        <h1>📖 Manga Notifier</h1>
        <p className="subtitle">Track new chapters automatically</p>
      </div>

      {mode === "signin" ? (
        <SignIn routing="hash" appearance={hideFooterAction} />
      ) : (
        <SignUp routing="hash" appearance={hideFooterAction} />
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
