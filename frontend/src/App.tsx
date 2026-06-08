import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { SignedIn, SignedOut, useAuth } from "@clerk/clerk-react";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import AddMangaPage from "./pages/AddMangaPage";
import SettingsPage from "./pages/SettingsPage";
import RedeemInvitePage from "./pages/RedeemInvitePage";
import { api, ApiError } from "./lib/api";
import { registerTokenGetter } from "./lib/auth-token";
import "./App.css";

function TokenBridge() {
  const { getToken } = useAuth();
  useEffect(() => {
    registerTokenGetter(() => getToken({ template: "default" }));
  }, [getToken]);
  return null;
}

type ProfileState = "loading" | "ok" | "invite_required" | "error";

function ProfileGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ProfileState>("loading");
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    api.getProfile()
      .then(() => { if (!cancelled) setState("ok"); })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 403 && err.detail === "invite_required") {
          setState("invite_required");
        } else {
          setState("error");
        }
      });
    return () => { cancelled = true; };
  }, [location.pathname]);

  if (state === "loading") return <div className="page">Loading...</div>;
  if (state === "invite_required") {
    if (location.pathname === "/redeem-invite") return <>{children}</>;
    return <Navigate to="/redeem-invite" replace />;
  }
  if (state === "error") return <div className="page">Could not load profile. Try refreshing.</div>;
  if (location.pathname === "/redeem-invite") return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <>
      <SignedOut>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </SignedOut>
      <SignedIn>
        <ProfileGate>
          <Routes>
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/redeem-invite" element={<RedeemInvitePage />} />
            <Route path="/" element={<DashboardPage />} />
            <Route path="/add" element={<AddMangaPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </ProfileGate>
      </SignedIn>
    </>
  );
}

function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <TokenBridge />
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
