import { useEffect, useMemo, useRef } from "react";
import { toLines } from "../lib.js";

export default function CodeViewer({ file, highlight, loading, error }) {
  const firstHighlighted = useRef(null);
  const lines = useMemo(() => (file ? toLines(file.text) : []), [file]);

  // When a citation is opened, scroll so its first line is in view.
  useEffect(() => {
    if (highlight && firstHighlighted.current) {
      firstHighlighted.current.scrollIntoView({ block: "center" });
    }
  }, [file, highlight]);

  if (error) return <p className="error-text pad">{error}</p>;
  if (loading) return <p className="muted pad">Loading file…</p>;
  if (!file) {
    return <p className="muted pad">Pick a file, or click a citation in an answer, to see the code here.</p>;
  }

  return (
    <div className="viewer">
      <div className="viewer-head">
        <strong>{file.path}</strong>
        {highlight && (
          <span className="pill">
            lines {highlight.start}–{highlight.end}
          </span>
        )}
      </div>
      <div className="code" role="region" aria-label={`Source of ${file.path}`}>
        {lines.map((text, index) => {
          const number = index + 1;
          const marked = highlight && number >= highlight.start && number <= highlight.end;
          return (
            <div
              key={number}
              className={"line" + (marked ? " hl" : "")}
              ref={highlight && number === highlight.start ? firstHighlighted : null}
            >
              <span className="no">{number}</span>
              <span className="src">{text || " "}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
