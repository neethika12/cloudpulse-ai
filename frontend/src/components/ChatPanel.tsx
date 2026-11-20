import { Fragment, useEffect, useRef, useState } from "react";
import {
  MessageSquare,
  Sparkles,
  Send,
  User,
  AlertCircle,
  Trash2,
  Database,
  BookOpen,
  Loader2,
  Square,
} from "lucide-react";
import {
  streamChat,
  ChatEvent,
  ChatRole,
  ChatUsage,
  Citation,
  ToolStep,
} from "../api/client";

interface Message {
  role: ChatRole;
  text: string;
  steps?: ToolStep[];
  citations?: Citation[];
  usage?: ChatUsage;
  streaming?: boolean;
  failed?: boolean;
}

const SUGGESTIONS = [
  "Which service costs the most?",
  "Why did spend spike recently, and what should I check?",
  "Compare the last 30 days to the 30 days before",
  "How can I cut my NAT gateway and data transfer costs?",
];

const TOOL_LABELS: Record<string, string> = {
  get_cost_summary: "Cost summary",
  get_daily_costs: "Daily costs",
  compare_periods: "Compare periods",
  get_anomalies: "Anomalies",
  search_knowledge_base: "Knowledge base",
};

function describeArgs(step: ToolStep): string {
  if (step.name === "search_knowledge_base") return `"${String(step.args.query ?? "")}"`;
  return Object.entries(step.args)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(", ");
}

function formatUsage(usage: ChatUsage): string {
  const parts = [
    `${(usage.latency_ms / 1000).toFixed(1)}s`,
    `${(usage.prompt_tokens + usage.completion_tokens).toLocaleString()} tokens`,
  ];
  if (usage.cost_usd !== null) parts.push(`$${usage.cost_usd.toFixed(4)}`);
  parts.push(`${usage.llm_calls} model call${usage.llm_calls === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

/** Inline markdown (**bold**, `code`) plus [K1]-style refs rendered as citation badges. */
function Inline({ text, citations }: { text: string; citations?: Citation[] }) {
  const known = new Set((citations ?? []).map((c) => c.ref));
  const parts = text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\[K\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const ref = part.match(/^\[(K\d+)\]$/)?.[1];
        if (ref && known.has(ref)) {
          return (
            <a key={i} className="cite-ref" href={`#cite-${ref}`} title="Jump to source">
              {ref}
            </a>
          );
        }
        if (ref && !citations) {
          // Still streaming: we don't know yet which refs are real.
          return (
            <span key={i} className="cite-ref static">
              {ref}
            </span>
          );
        }
        if (ref) return null;
        if (/^\*\*[^*\n]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
        if (/^`[^`\n]+`$/.test(part)) return <code key={i}>{part.slice(1, -1)}</code>;
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </>
  );
}

type Block =
  | { kind: "p"; text: string }
  | { kind: "h"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] };

/** Small markdown subset: headings, bullet/numbered lists and paragraphs. */
function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let gap = false; // a blank line was seen since the last block line
  for (const line of text.split("\n")) {
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const last = blocks[blocks.length - 1];
    if (line.trim() === "") {
      gap = true; // lists continue across blank lines; paragraphs end here
      continue;
    }
    if (heading) blocks.push({ kind: "h", text: heading[1] });
    else if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? numbered)![1];
      if (last && last.kind === kind) last.items.push(item);
      else blocks.push({ kind, items: [item] });
    } else if (last && last.kind === "p" && !gap) {
      last.text += "\n" + line;
    } else blocks.push({ kind: "p", text: line });
    gap = false;
  }
  return blocks;
}

function AnswerText({ text, citations }: { text: string; citations?: Citation[] }) {
  return (
    <div className="answer-md">
      {parseBlocks(text).map((b, i) => {
        if (b.kind === "h") {
          return (
            <h4 key={i}>
              <Inline text={b.text} citations={citations} />
            </h4>
          );
        }
        if (b.kind === "ul" || b.kind === "ol") {
          const List = b.kind;
          return (
            <List key={i}>
              {b.items.map((item, j) => (
                <li key={j}>
                  <Inline text={item} citations={citations} />
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={i}>
            <Inline text={b.text} citations={citations} />
          </p>
        );
      })}
    </div>
  );
}

function ToolTrace({ steps }: { steps: ToolStep[] }) {
  return (
    <div className="tool-trace">
      {steps.map((step) => {
        const isSearch = step.name === "search_knowledge_base";
        const pending = step.summary === undefined;
        return (
          <div className="tool-step" key={step.id}>
            {pending ? (
              <Loader2 size={12} className="spin" />
            ) : isSearch ? (
              <BookOpen size={12} />
            ) : (
              <Database size={12} />
            )}
            <span className="tool-name">{TOOL_LABELS[step.name] ?? step.name}</span>
            {describeArgs(step) && <span className="tool-args">{describeArgs(step)}</span>}
            {!pending && (
              <span className="tool-result">
                → {step.summary}
                {step.latency_ms !== undefined && ` · ${step.latency_ms}ms`}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Sources({ citations }: { citations: Citation[] }) {
  return (
    <div className="chat-sources">
      <div className="chat-sources-label">Sources</div>
      {citations.map((c) => (
        <details key={c.ref} id={`cite-${c.ref}`} className="source-item">
          <summary>
            <span className="cite-ref static">{c.ref}</span>
            <span className="source-title">{c.title}</span>
            <span className="source-section">› {c.section}</span>
          </summary>
          <p>{c.snippet}</p>
          <code>{c.source}</code>
        </details>
      ))}
    </div>
  );
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const updateLast = (fn: (m: Message) => Message) =>
    setMessages((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1])]);

  const handleEvent = (event: ChatEvent) => {
    switch (event.type) {
      case "tool_call":
        // Any text the model wrote before deciding to call a tool is not the answer.
        updateLast((m) => ({ ...m, text: "", steps: [...(m.steps ?? []), { ...event }] }));
        break;
      case "tool_result":
        updateLast((m) => ({
          ...m,
          steps: (m.steps ?? []).map((s) => (s.id === event.id ? { ...s, ...event } : s)),
        }));
        break;
      case "token":
        updateLast((m) => ({ ...m, text: m.text + event.text }));
        break;
      case "done":
        updateLast((m) => ({
          ...m,
          text: event.answer,
          steps: event.steps,
          citations: event.citations,
          usage: event.usage,
          streaming: false,
        }));
        break;
      case "error":
        updateLast((m) => ({ ...m, streaming: false, failed: true }));
        setError(event.detail);
        break;
    }
  };

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || asking) return;

    const history = messages
      .filter((m) => !m.failed && m.text)
      .map((m) => ({ role: m.role, content: m.text }));
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "", steps: [], streaming: true },
    ]);
    setInput("");
    setAsking(true);
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(question, history, handleEvent, controller.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
      updateLast((m) => ({ ...m, streaming: false, failed: !m.text }));
    } finally {
      abortRef.current = null;
      setAsking(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") ask(input);
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2>
          <MessageSquare size={16} />
          Chat with your cloud spend
        </h2>
        <div className="card-actions">
          <button
            className="btn secondary"
            onClick={() => {
              setMessages([]);
              setError(null);
            }}
            disabled={asking || messages.length === 0}
          >
            <Trash2 size={14} />
            Clear
          </button>
        </div>
      </div>

      {error && (
        <div className="status-line error" style={{ marginBottom: 12 }}>
          <AlertCircle size={13} />
          {error}
        </div>
      )}

      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <Sparkles size={32} />
            <div>
              Ask about your AWS spend. Numbers come from SQL queries on your cost data; advice
              comes from a FinOps knowledge base, with sources.
            </div>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn secondary" onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`chat-row ${m.role}`} key={i}>
            <div className={`chat-avatar ${m.role}`}>
              {m.role === "user" ? <User size={15} /> : <Sparkles size={15} />}
            </div>
            <div className="chat-message">
              {m.steps && m.steps.length > 0 && <ToolTrace steps={m.steps} />}
              {(m.text || m.role === "user") && (
                <div className={`chat-bubble ${m.role}`} style={m.role === "user" ? { whiteSpace: "pre-wrap" } : undefined}>
                  {m.role === "assistant" ? (
                    <AnswerText text={m.text} citations={m.citations} />
                  ) : (
                    m.text
                  )}
                  {m.streaming && <span className="caret" />}
                </div>
              )}
              {m.streaming && !m.text && (m.steps?.length ?? 0) === 0 && (
                <div className="chat-bubble assistant thinking">Thinking…</div>
              )}
              {m.citations && m.citations.length > 0 && <Sources citations={m.citations} />}
              {m.usage && <div className="chat-usage">{formatUsage(m.usage)}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your cloud spend…"
          disabled={asking}
        />
        {asking ? (
          <button className="btn secondary" onClick={() => abortRef.current?.abort()}>
            <Square size={14} />
            Stop
          </button>
        ) : (
          <button className="btn" onClick={() => ask(input)} disabled={!input.trim()}>
            <Send size={14} />
            Send
          </button>
        )}
      </div>
    </div>
  );
}
