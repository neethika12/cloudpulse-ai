import { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  BookOpen,
  Coins,
  Gauge,
  Hash,
  RefreshCw,
  Timer,
  Wrench,
} from "lucide-react";
import { api, KnowledgeStatus, UsageReport } from "../api/client";

const TOOL_LABELS: Record<string, string> = {
  get_cost_summary: "Cost summary",
  get_daily_costs: "Daily costs",
  compare_periods: "Compare periods",
  get_anomalies: "Anomalies",
  search_knowledge_base: "Knowledge base",
};

export default function UsagePanel() {
  const [report, setReport] = useState<UsageReport | null>(null);
  const [kb, setKb] = useState<KnowledgeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [reindexResult, setReindexResult] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [usage, status] = await Promise.all([api.llmUsage(), api.knowledgeStatus()]);
      setReport(usage);
      setKb(status);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleReindex = async () => {
    setReindexing(true);
    setReindexResult(null);
    setError(null);
    try {
      const res = await api.reindexKnowledge();
      setReindexResult(`${res.added} added, ${res.unchanged} unchanged, ${res.removed} removed`);
      setKb(await api.knowledgeStatus());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setReindexing(false);
    }
  };

  const s = report?.summary;
  const maxToolCalls = Math.max(1, ...(report?.tools.map((t) => t.calls) ?? [1]));

  return (
    <div>
      {error && (
        <div className="card">
          <div className="status-line error" style={{ marginTop: 0 }}>
            <AlertCircle size={13} />
            {error}
          </div>
        </div>
      )}

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-icon">
            <Hash size={17} />
          </div>
          <div className="stat-label">Chat requests</div>
          <div className="stat-value">{s ? s.requests : "—"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">
            <Coins size={17} />
          </div>
          <div className="stat-label">LLM cost</div>
          <div className="stat-value">{s ? `$${s.cost_usd.toFixed(4)}` : "—"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">
            <Activity size={17} />
          </div>
          <div className="stat-label">Tokens (in / out)</div>
          <div className="stat-value small">
            {s ? `${s.prompt_tokens.toLocaleString()} / ${s.completion_tokens.toLocaleString()}` : "—"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">
            <Timer size={17} />
          </div>
          <div className="stat-label">Latency p50 / p95</div>
          <div className="stat-value small">
            {s ? `${(s.p50_latency_ms / 1000).toFixed(1)}s / ${(s.p95_latency_ms / 1000).toFixed(1)}s` : "—"}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <h2>
              <Wrench size={16} />
              Tool usage
            </h2>
            {s && (
              <span className="muted-note">
                {s.avg_tool_calls} tools per question · {s.cited_answers} cited answers ·{" "}
                {s.errors} errors
              </span>
            )}
          </div>
          {report && report.tools.length === 0 && (
            <div className="empty-state">No tool calls yet. Ask something in Chat.</div>
          )}
          {report?.tools.map((t) => (
            <div className="bar-row" key={t.name}>
              <span className="bar-label">{TOOL_LABELS[t.name] ?? t.name}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(t.calls / maxToolCalls) * 100}%` }} />
              </div>
              <span className="bar-value">{t.calls}</span>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-header">
            <h2>
              <BookOpen size={16} />
              Knowledge base
            </h2>
            <div className="card-actions">
              <button className="btn secondary" onClick={handleReindex} disabled={reindexing}>
                <RefreshCw size={14} className={reindexing ? "spin" : undefined} />
                {reindexing ? "Indexing…" : "Re-index"}
              </button>
            </div>
          </div>
          {kb && (
            <>
              <div className="kb-stats">
                <div>
                  <strong>{kb.documents}</strong>/{kb.documents_on_disk} guides indexed
                </div>
                <div>
                  <strong>{kb.chunks}</strong> chunks
                </div>
                <div>
                  <code>{kb.embedding_model}</code>
                </div>
              </div>
              <div className="kb-sources">
                {kb.sources.map((src) => (
                  <span className="kb-source" key={src}>
                    {src.replace(/\.md$/, "")}
                  </span>
                ))}
              </div>
              <p className="muted-note" style={{ marginTop: 14 }}>
                Hybrid retrieval: pgvector cosine search + Postgres full-text search, merged with
                reciprocal rank fusion, then reranked by an LLM. Re-indexing only embeds changed
                chunks. {kb.chunks === 0 && "The index builds itself on the first knowledge question."}
              </p>
            </>
          )}
          {reindexResult && <div className="status-line">{reindexResult}</div>}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>
            <Gauge size={16} />
            Recent requests
          </h2>
          <button className="btn secondary" onClick={load}>
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
        {report && report.recent.length === 0 && (
          <div className="empty-state">No chat requests yet.</div>
        )}
        {report && report.recent.length > 0 && (
          <div className="table-wrap">
            <table className="trace-table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Tools</th>
                  <th className="num">Sources</th>
                  <th className="num">Tokens</th>
                  <th className="num">Cost</th>
                  <th className="num">Latency</th>
                </tr>
              </thead>
              <tbody>
                {report.recent.map((r) => (
                  <tr key={r.id} className={r.status !== "ok" ? "failed" : undefined}>
                    <td className="question" title={r.question}>
                      {r.status !== "ok" && <span className="status-pill">error</span>}
                      {r.question}
                    </td>
                    <td className="tools">
                      {r.tools.length ? r.tools.map((t) => TOOL_LABELS[t] ?? t).join(", ") : "—"}
                    </td>
                    <td className="num">{r.citations}</td>
                    <td className="num">{r.tokens.toLocaleString()}</td>
                    <td className="num">{r.cost_usd === null ? "—" : `$${r.cost_usd.toFixed(4)}`}</td>
                    <td className="num">{(r.latency_ms / 1000).toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
