import { useCallback, useEffect, useRef, useState } from "react";
import { addRepo, askQuestion, getFile, getStatus } from "./api.js";
import Chat from "./components/Chat.jsx";
import CodeViewer from "./components/CodeViewer.jsx";
import FileTree from "./components/FileTree.jsx";
import RepoForm from "./components/RepoForm.jsx";
import StatusBar from "./components/StatusBar.jsx";

const WORKING = ["queued", "indexing"];

export default function App() {
  const [status, setStatus] = useState(null);       // what the backend says about the repo
  const [formError, setFormError] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const [file, setFile] = useState(null);           // the file shown in the viewer
  const [highlight, setHighlight] = useState(null); // {start, end} or null
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState("");
  const cache = useRef(new Map());                  // files we already downloaded

  const repo = status?.repo;
  const working = status ? WORKING.includes(status.state) : false;

  // Poll the backend while indexing. The cleanup stops the timer when we are done.
  useEffect(() => {
    if (!repo || !working) return;
    const timer = setInterval(async () => {
      try {
        setStatus(await getStatus(repo));
      } catch (err) {
        setStatus((s) => ({ ...s, state: "failed", error: err.message }));
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [repo, working]);

  async function analyze(url) {
    setFormError("");
    try {
      const next = await addRepo(url);
      if (next.repo !== repo) {
        // a different repository: start with a clean screen
        setMessages([]);
        setFile(null);
        setHighlight(null);
        cache.current.clear();
      }
      setStatus(next);
    } catch (err) {
      setFormError(err.message);
    }
  }

  const openFile = useCallback(
    async (path, range = null) => {
      setHighlight(range);
      setFileError("");
      const key = `${repo}:${path}`;
      if (cache.current.has(key)) {
        setFile(cache.current.get(key));
        return;
      }
      setFileLoading(true);
      try {
        const loaded = await getFile(repo, path);
        cache.current.set(key, loaded);
        setFile(loaded);
      } catch (err) {
        setFileError(err.message);
      } finally {
        setFileLoading(false);
      }
    },
    [repo]
  );

  async function ask(question) {
    setMessages((m) => [...m, { role: "user", text: question }]);
    setAsking(true);
    try {
      const response = await askQuestion(repo, question);
      setMessages((m) => [...m, { role: "assistant", response }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
    } finally {
      setAsking(false);
    }
  }

  const openCitation = (c) => openFile(c.path, { start: c.start_line, end: c.end_line });

  return (
    <div className="app">
      <header className="top">
        <h1>RepoMind</h1>
        <RepoForm onSubmit={analyze} busy={working} />
      </header>
      {formError && <p className="banner error-text">{formError}</p>}
      <StatusBar status={status} />

      <main className="panes">
        <section className="pane tree-pane" aria-label="Files">
          <h2>Files</h2>
          {/* key makes the tree start fresh for each repository */}
          <FileTree
            key={repo}
            files={status?.files ?? []}
            selected={file?.path}
            onSelect={(path) => openFile(path)}
          />
        </section>
        <section className="pane chat-pane" aria-label="Chat">
          <h2>Ask</h2>
          <Chat
            messages={messages}
            busy={asking}
            disabled={status?.state !== "ready"}
            onAsk={ask}
            onOpen={openCitation}
          />
        </section>
        <section className="pane code-pane" aria-label="Code">
          <h2>Code</h2>
          <CodeViewer file={file} highlight={highlight} loading={fileLoading} error={fileError} />
        </section>
      </main>
    </div>
  );
}
