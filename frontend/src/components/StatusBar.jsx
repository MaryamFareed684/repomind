const LABELS = {
  queued: "Waiting to start…",
  indexing: "Reading and embedding the code…",
  ready: "Ready",
  failed: "Failed",
};

export default function StatusBar({ status }) {
  if (!status) return null;
  const percent = status.total ? Math.round((status.done / status.total) * 100) : 0;
  const languages = Object.entries(status.languages || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([name, count]) => `${name} ${count}`)
    .join(" · ");

  return (
    <div className={`status status-${status.state}`} role="status">
      <strong>{status.repo}</strong>
      <span className="muted">{status.branch}</span>
      <span className="pill">{LABELS[status.state]}</span>
      {status.state === "indexing" && status.total > 0 && (
        <span className="progress" aria-label={`${percent}% embedded`}>
          <span className="progress-fill" style={{ width: `${percent}%` }} />
        </span>
      )}
      {status.state === "ready" && (
        <span className="muted">
          {status.file_count} files · {status.chunk_count} chunks{languages && ` · ${languages}`}
        </span>
      )}
      {status.state === "failed" && <span className="error-text">{status.error}</span>}
    </div>
  );
}
