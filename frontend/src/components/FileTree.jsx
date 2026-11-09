import { useMemo, useState } from "react";
import { buildTree } from "../lib.js";

function Node({ node, depth, open, toggle, selected, onSelect }) {
  const pad = { paddingLeft: 8 + depth * 14 };
  if (node.type === "file") {
    return (
      <button
        className={"tree-row file" + (node.path === selected ? " selected" : "")}
        style={pad}
        onClick={() => onSelect(node.path)}
        title={node.path}
      >
        {node.name}
      </button>
    );
  }
  const isOpen = open.has(node.path);
  return (
    <>
      <button className="tree-row dir" style={pad} onClick={() => toggle(node.path)}>
        <span className="caret">{isOpen ? "▾" : "▸"}</span> {node.name}
      </button>
      {isOpen &&
        node.children.map((child) => (
          <Node
            key={child.path}
            node={child}
            depth={depth + 1}
            open={open}
            toggle={toggle}
            selected={selected}
            onSelect={onSelect}
          />
        ))}
    </>
  );
}

export default function FileTree({ files, selected, onSelect }) {
  const tree = useMemo(() => buildTree(files), [files]);
  // Top-level folders start open; the folder of the selected file is opened too.
  const [open, setOpen] = useState(() => new Set(tree.filter((n) => n.type === "dir").map((n) => n.path)));

  const openWithParents = useMemo(() => {
    const all = new Set(open);
    if (selected) {
      const parts = selected.split("/").slice(0, -1);
      parts.forEach((_, i) => all.add(parts.slice(0, i + 1).join("/")));
    }
    return all;
  }, [open, selected]);

  function toggle(path) {
    setOpen((current) => {
      const next = new Set(openWithParents);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  }

  if (!files.length) return <p className="muted pad">No files yet.</p>;
  return (
    <nav className="tree" aria-label="Files">
      {tree.map((node) => (
        <Node
          key={node.path}
          node={node}
          depth={0}
          open={openWithParents}
          toggle={toggle}
          selected={selected}
          onSelect={onSelect}
        />
      ))}
    </nav>
  );
}
