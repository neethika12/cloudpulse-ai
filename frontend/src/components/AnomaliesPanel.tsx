import { useEffect, useState } from "react";
import { AlertTriangle, ShieldCheck, Radar, Send, AlertCircle } from "lucide-react";
import { api, Anomaly } from "../api/client";

export default function AnomaliesPanel() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [alertStatus, setAlertStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setAnomalies(await api.listAnomalies());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDetect = async () => {
    setDetecting(true);
    setError(null);
    setAlertStatus(null);
    try {
      setAnomalies(await api.detectAnomalies());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDetecting(false);
    }
  };

  const handleAlert = async () => {
    setAlertStatus(null);
    setError(null);
    try {
      const res = await api.sendAlert();
      setAlertStatus(res.detail);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2>
          <AlertTriangle size={16} />
          Cost anomalies
        </h2>
        <div className="card-actions">
          <button className="btn" onClick={handleDetect} disabled={detecting}>
            <Radar size={14} />
            {detecting ? "Running detection…" : "Run anomaly detection"}
          </button>
          <button
            className="btn secondary"
            onClick={handleAlert}
            disabled={anomalies.length === 0}
          >
            <Send size={14} />
            Send Slack alert
          </button>
        </div>
      </div>

      {error && (
        <div className="status-line error">
          <AlertCircle size={13} />
          {error}
        </div>
      )}
      {alertStatus && <div className="status-line">{alertStatus}</div>}

      {!loading && anomalies.length === 0 && (
        <div className="empty-state">
          <ShieldCheck size={32} />
          <div>
            No anomalies flagged yet. Seed cost data on the Dashboard tab, then run
            detection.
          </div>
        </div>
      )}

      {anomalies.map((a, i) => (
        <div className="anomaly-row" key={`${a.service}-${a.date}-${i}`}>
          <div className="anomaly-left">
            <span className="service-badge">{a.service}</span>
            <span className="date">{a.date}</span>
          </div>
          <span className="amount">${a.amount_usd.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}
