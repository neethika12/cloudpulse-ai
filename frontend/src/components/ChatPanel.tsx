import { useState } from "react";
import { MessageSquare, Sparkles, Database, Send, User, AlertCircle } from "lucide-react";
import { api } from "../api/client";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleIndex = async () => {
    setIndexing(true);
    setError(null);
    try {
      const res = await api.indexChat();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Indexed ${res.indexed} cost summaries. Ask away.` },
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIndexing(false);
    }
  };

  const handleAsk = async () => {
    const question = input.trim();
    if (!question || asking) return;

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setAsking(true);
    setError(null);

    try {
      const res = await api.ask(question);
      setMessages((prev) => [...prev, { role: "assistant", text: res.answer }]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAsking(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleAsk();
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2>
          <MessageSquare size={16} />
          Chat with your cloud spend
        </h2>
        <div className="card-actions">
          <button className="btn secondary" onClick={handleIndex} disabled={indexing}>
            <Database size={14} />
            {indexing ? "Indexing…" : "Index current cost data"}
          </button>
        </div>
      </div>

      {error && (
        <div className="status-line error">
          <AlertCircle size={13} />
          {error}
        </div>
      )}

      <div className="chat-log">
        {messages.length === 0 && (
          <div className="empty-state">
            <Sparkles size={32} />
            <div>
              Index your cost data first, then ask things like "which service costs the
              most?" or "how much did EC2 cost this month?"
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`chat-row ${m.role}`} key={i}>
            <div className={`chat-avatar ${m.role}`}>
              {m.role === "user" ? <User size={15} /> : <Sparkles size={15} />}
            </div>
            <div className={`chat-bubble ${m.role}`}>{m.text}</div>
          </div>
        ))}
        {asking && (
          <div className="chat-row assistant">
            <div className="chat-avatar assistant">
              <Sparkles size={15} />
            </div>
            <div className="chat-bubble assistant thinking">Thinking…</div>
          </div>
        )}
      </div>

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your cloud spend…"
          disabled={asking}
        />
        <button className="btn" onClick={handleAsk} disabled={asking || !input.trim()}>
          <Send size={14} />
          Send
        </button>
      </div>
    </div>
  );
}
