import { useState } from "react";
import {
  Sparkles,
  BarChart3,
  AlertTriangle,
  MessageSquare,
  Settings,
  ArrowRight,
  Check,
} from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import "./OnboardingTour.css";

type Tab = "dashboard" | "anomalies" | "chat" | "settings";

interface Step {
  icon: typeof Sparkles;
  title: string;
  body: string;
  tab?: Tab;
}

const STEPS: Step[] = [
  {
    icon: Sparkles,
    title: "Welcome to CloudPulse AI",
    body: "This is a quick tour of what you can do here. It only takes a minute — you can skip it any time.",
  },
  {
    icon: BarChart3,
    title: "See your cost dashboard",
    body: 'Seed some sample AWS cost data to see charts by service and over time. Once you connect a real AWS account in Settings, this fills in with your actual spend.',
    tab: "dashboard",
  },
  {
    icon: AlertTriangle,
    title: "Catch spending spikes automatically",
    body: "A scikit-learn model watches your daily spend per service and flags anything unusual, so surprise bills don't sneak up on you.",
    tab: "anomalies",
  },
  {
    icon: MessageSquare,
    title: "Ask questions in plain English",
    body: 'Index your cost data, then ask things like "which service costs the most?" — answered by a local AI pipeline, no API key required.',
    tab: "chat",
  },
  {
    icon: Settings,
    title: "Connect your real AWS account",
    body: "Add your AWS credentials to pull real Cost Explorer data, and set a Slack webhook to get notified when anomalies are detected.",
    tab: "settings",
  },
];

export default function OnboardingTour({ onNavigate }: { onNavigate: (tab: Tab) => void }) {
  const { refreshUser } = useAuth();
  const [stepIndex, setStepIndex] = useState(0);
  const [finishing, setFinishing] = useState(false);

  const step = STEPS[stepIndex];
  const isLast = stepIndex === STEPS.length - 1;

  const finish = async () => {
    setFinishing(true);
    try {
      await api.updateProfile({ onboarding_completed: true });
      await refreshUser();
    } finally {
      setFinishing(false);
    }
  };

  const handleNext = () => {
    if (step.tab) onNavigate(step.tab);
    if (isLast) {
      finish();
    } else {
      setStepIndex((i) => i + 1);
    }
  };

  return (
    <div className="tour-backdrop">
      <div className="tour-card">
        <div className="tour-icon">
          <step.icon size={20} />
        </div>
        <h3>{step.title}</h3>
        <p>{step.body}</p>

        <div className="tour-dots">
          {STEPS.map((_, i) => (
            <span key={i} className={`tour-dot ${i === stepIndex ? "active" : ""}`} />
          ))}
        </div>

        <div className="tour-actions">
          <button className="tour-skip" onClick={finish} disabled={finishing}>
            Skip tour
          </button>
          <button className="btn" onClick={handleNext} disabled={finishing}>
            {isLast ? (
              <>
                <Check size={14} />
                Done
              </>
            ) : (
              <>
                Next
                <ArrowRight size={14} />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
