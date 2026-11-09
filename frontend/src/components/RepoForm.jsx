import { useState } from "react";

export default function RepoForm({ onSubmit, busy }) {
  const [url, setUrl] = useState("");

  function handleSubmit(event) {
    event.preventDefault(); // stop the browser from reloading the page
    if (url.trim()) onSubmit(url.trim());
  }

  return (
    <form className="repo-form" onSubmit={handleSubmit}>
      <input
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://github.com/owner/repository"
        aria-label="GitHub repository URL"
        disabled={busy}
      />
      <button type="submit" disabled={busy || !url.trim()}>
        {busy ? "Indexing…" : "Analyze"}
      </button>
    </form>
  );
}
