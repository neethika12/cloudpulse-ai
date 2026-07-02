import {
  Cloud,
  ArrowRight,
  BarChart3,
  MessageSquare,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import "./LandingPage.css";

const FEATURES = [
  {
    icon: BarChart3,
    title: "Real-time cost dashboards",
    description: "Track AWS spend by service and over time with live, interactive charts.",
  },
  {
    icon: MessageSquare,
    title: "Chat with your cloud spend",
    description:
      "Ask questions in plain English, answered by a local RAG pipeline built on LangChain and pgvector.",
  },
  {
    icon: AlertTriangle,
    title: "ML-powered anomaly detection",
    description:
      "A scikit-learn IsolationForest flags unusual spending spikes before they become a surprise bill.",
  },
  {
    icon: ShieldCheck,
    title: "Secure by design",
    description: "JWT authentication with bcrypt-hashed passwords protects every account.",
  },
];

export default function LandingPage({ onGetStarted }: { onGetStarted: () => void }) {
  return (
    <div className="landing">
      <nav className="landing-nav">
        <div className="landing-brand">
          <div className="brand-icon">
            <Cloud size={18} strokeWidth={2.5} />
          </div>
          <span>CloudPulse AI</span>
        </div>
        <button className="btn secondary" onClick={onGetStarted}>
          Sign in
        </button>
      </nav>

      <section className="hero">
        <div className="hero-badge">AI-powered AWS cost monitoring</div>
        <h1>
          Understand your cloud spend
          <br />
          before it surprises you.
        </h1>
        <p>
          CloudPulse AI watches your AWS costs, explains them in plain English, and
          catches unusual spikes automatically — so you're never caught off guard by a
          bill.
        </p>
        <div className="hero-actions">
          <button className="btn hero-cta" onClick={onGetStarted}>
            Get started
            <ArrowRight size={16} />
          </button>
        </div>
      </section>

      <section className="feature-grid">
        {FEATURES.map((f) => (
          <div className="feature-card" key={f.title}>
            <div className="feature-icon">
              <f.icon size={18} />
            </div>
            <h3>{f.title}</h3>
            <p>{f.description}</p>
          </div>
        ))}
      </section>

      <footer className="landing-footer">
        Built with FastAPI, PostgreSQL + pgvector, LangChain, scikit-learn, and React.
      </footer>
    </div>
  );
}
