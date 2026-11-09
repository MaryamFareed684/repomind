// All talking to the backend happens here, so components never build URLs themselves.
const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function request(path, options) {
  let response;
  try {
    response = await fetch(BASE + path, options);
  } catch {
    throw new Error(`Cannot reach the backend at ${BASE}. Is it running?`);
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    /* the body was not JSON */
  }
  if (!response.ok) {
    // FastAPI sends {detail: "text"}; validation errors send a list instead.
    const detail = body && typeof body.detail === "string" ? body.detail : null;
    throw new Error(detail || `The server answered with an error (${response.status}).`);
  }
  return body;
}

const json = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

// repo is "owner/name"; encode each part so odd characters cannot break the URL
const repoPath = (repo) => "/repos/" + repo.split("/").map(encodeURIComponent).join("/");

export const addRepo = (url, refresh = false) => request("/repos", json({ url, refresh }));
export const getStatus = (repo) => request(repoPath(repo));
export const getFile = (repo, path) =>
  request(`${repoPath(repo)}/file?path=${encodeURIComponent(path)}`);
export const askQuestion = (repo, question) =>
  request(`${repoPath(repo)}/ask`, json({ question }));
