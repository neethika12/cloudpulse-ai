import { useEffect, useState } from "react";
import {
  Cloud,
  LayoutDashboard,
  AlertTriangle,
  MessageSquare,
  Settings,
  LogOut,
} from "lucide-react";
import "./App.css";
import Dashboard from "./components/Dashboard";
import AnomaliesPanel from "./components/AnomaliesPanel";
import ChatPanel from "./components/ChatPanel";
import SettingsPanel from "./components/SettingsPanel";
import OnboardingTour from "./onboarding/OnboardingTour";
import { api } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import AuthPage from "./auth/AuthPage";
import LandingPage from "./landing/LandingPage";

type Tab = "dashboard" | "anomalies" | "chat" | "settings";

const PAGE_META: Record<Tab, { title: string; subtitle: string }> = {
  dashboard: {
    title: "Dashboard",
    subtitle: "Real-time overview of your AWS spend",
  },
  anomalies: {
    title: "Anomalies",
    subtitle: "ML-detected unusual spending patterns",
  },
  chat: {
    title: "Chat",
    subtitle: "Ask questions about your cloud costs in plain English",
  },
  settings: {
    title: "Settings",
    subtitle: "Connect AWS and configure Slack alerts",
  },
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function Shell() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [anomalyCount, setAnomalyCount] = useState(0);

  useEffect(() => {
    api
      .listAnomalies()
      .then((list) => setAnomalyCount(list.length))
      .catch(() => setAnomalyCount(0));
  }, [tab]);

  const meta = PAGE_META[tab];
  const displayName = user?.full_name || user?.email || "Account";

  return (
    <div className="shell">
      {user && !user.onboarding_completed && <OnboardingTour onNavigate={setTab} />}

      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">
            <Cloud size={19} strokeWidth={2.5} />
          </div>
          <div>
            <h1>CloudPulse AI</h1>
            <p>AWS cost monitoring</p>
          </div>
        </div>

        <div className="nav-section-label">Menu</div>
        <nav className="nav">
          <button
            className={`nav-item ${tab === "dashboard" ? "active" : ""}`}
            onClick={() => setTab("dashboard")}
          >
            <LayoutDashboard size={16} />
            Dashboard
          </button>
          <button
            className={`nav-item ${tab === "anomalies" ? "active" : ""}`}
            onClick={() => setTab("anomalies")}
          >
            <AlertTriangle size={16} />
            Anomalies
            {anomalyCount > 0 && <span className="nav-badge">{anomalyCount}</span>}
          </button>
          <button
            className={`nav-item ${tab === "chat" ? "active" : ""}`}
            onClick={() => setTab("chat")}
          >
            <MessageSquare size={16} />
            Chat
          </button>
          <button
            className={`nav-item ${tab === "settings" ? "active" : ""}`}
            onClick={() => setTab("settings")}
          >
            <Settings size={16} />
            Settings
          </button>
        </nav>

        <div className="sidebar-spacer" />

        <div className="sidebar-footer">
          <div className="account-card">
            <div className="account-avatar">{initials(displayName)}</div>
            <div className="account-info">
              <div className="account-name">{displayName}</div>
              <div className="account-meta">{user?.email}</div>
            </div>
            <button className="logout-btn" onClick={logout} title="Log out">
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div>
            <h2 className="page-title">{meta.title}</h2>
            <p className="page-subtitle">{meta.subtitle}</p>
          </div>
          <div className="live-badge">
            <span className="live-dot" />
            Local environment
          </div>
        </div>

        <div className="page-content">
          {tab === "dashboard" && <Dashboard />}
          {tab === "anomalies" && <AnomaliesPanel />}
          {tab === "chat" && <ChatPanel />}
          {tab === "settings" && <SettingsPanel />}
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  const [showAuth, setShowAuth] = useState(false);

  if (loading) return null;
  if (user) return <Shell />;
  if (showAuth) return <AuthPage />;
  return <LandingPage onGetStarted={() => setShowAuth(true)} />;
}
