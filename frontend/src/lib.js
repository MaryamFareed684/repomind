// Small pure helpers (no React), easy to test.

/** Turn a flat list of files into a nested folder tree. Folders first, then files, A-Z. */
export function buildTree(files) {
  const root = { name: "", path: "", type: "dir", children: [] };
  for (const file of files) {
    const parts = file.path.split("/");
    let node = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      const isFile = index === parts.length - 1;
      let child = node.children.find((c) => c.name === part && c.type === (isFile ? "file" : "dir"));
      if (!child) {
        child = { name: part, path, type: isFile ? "file" : "dir", children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sortNode = (node) => {
    node.children.sort((a, b) =>
      a.type !== b.type ? (a.type === "dir" ? -1 : 1) : a.name.localeCompare(b.name)
    );
    node.children.forEach(sortNode);
  };
  sortNode(root);
  return root.children;
}

/** Cut an answer into pieces: plain text, `code`, and [1] / [2, 3] citations. */
export function splitAnswer(text) {
  const pieces = [];
  const pattern = /`([^`\n]+)`|\[(\d+(?:\s*,\s*\d+)*)\]/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) pieces.push({ type: "text", value: text.slice(last, match.index) });
    if (match[1] !== undefined) {
      pieces.push({ type: "code", value: match[1] });
    } else {
      const numbers = match[2].split(",").map((n) => parseInt(n, 10));
      pieces.push({ type: "cite", value: match[0], numbers });
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) pieces.push({ type: "text", value: text.slice(last) });
  return pieces;
}

/** "app/store.py:40-62" */
export const citationLabel = (c) => `${c.path}:${c.start_line}-${c.end_line}`;

/** The lines of a file, numbered from 1, the same way the backend counts them. */
export function toLines(text) {
  return text.split("\n").map((line) => line.replace(/\r$/, ""));
}
