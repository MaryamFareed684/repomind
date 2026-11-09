import { useEffect, useRef, useState } from "react";
import { citationLabel, splitAnswer } from "../lib.js";

const BADGES = {
  answered: { text: "Citations verified", className: "ok" },
  not_found: { text: "Not found in the repository", className: "neutral" },
  unverified: { text: "Could not fully verify citations", className: "warn" },
};

const SUGGESTIONS = [
  "How is this project organized?",
  "Where is the main entry point?",
  "How does error handling work?",
];

function Answer({ response, onOpen }) {
  const byNumber = new Map(response.citations.map((c) => [c.n, c]));
  const pieces = splitAnswer(response.answer);
  const badge = BADGES[response.status] || BADGES.unverified;

  return (
    <div>
      <p className="answer-text">
        {pieces.map((piece, i) => {
          if (piece.type === "code") return <code key={i}>{piece.value}</code>;
          if (piece.type === "cite") {
            const known = piece.numbers.map((n) => byNumber.get(n)).filter(Boolean);
            if (!known.length) return <span key={i}>{piece.value}</span>;
            return (
              <span key={i}>
                {known.map((c) => (
                  <button key={c.n} className="cite" title={citationLabel(c)} onClick={() => onOpen(c)}>
                    {c.n}
                  </button>
                ))}
              </span>
            );
          }
          return <span key={i}>{piece.value}</span>;
        })}
      </p>
      <span className={`badge ${badge.className}`}>{badge.text}</span>
      {response.problems.length > 0 && (
        <ul className="problems">
          {response.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      {response.citations.length > 0 && (
        <div className="sources">
          {response.citations.map((c) => (
            <button key={c.n} className="source" onClick={() => onOpen(c)}>
              [{c.n}] {citationLabel(c)}
            </button>
          ))}
        </div>
      )}
      {response.evidence.length > 0 && (
        <details className="evidence">
          <summary>Evidence the model saw ({response.evidence.length})</summary>
          <ol>
            {response.evidence.map((e) => (
              <li key={e.n}>
                {e.kind === "tree" ? "file tree" : citationLabel(e)}
                {e.symbol && e.symbol !== "<module>" ? ` · ${e.symbol}` : ""}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

export default function Chat({ messages, busy, disabled, onAsk, onOpen }) {
  const [text, setText] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  function submit(event) {
    event.preventDefault();
    const question = text.trim();
    if (!question || busy || disabled) return;
    setText("");
    onAsk(question);
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p className="muted">
              {disabled ? "Analyze a repository to start asking questions." : "Ask anything about this repository."}
            </p>
            {!disabled &&
              SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => onAsk(s)} disabled={busy}>
                  {s}
                </button>
              ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "user" && <p>{m.text}</p>}
            {m.role === "error" && <p className="error-text">{m.text}</p>}
            {m.role === "assistant" && <Answer response={m.response} onOpen={onOpen} />}
          </div>
        ))}
        {busy && <div className="msg assistant muted">Searching the code and writing an answer…</div>}
        <div ref={endRef} />
      </div>
      <form className="ask-form" onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={disabled ? "Index a repository first" : "Where is the login handled?"}
          aria-label="Your question"
          maxLength={500}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || busy || !text.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
