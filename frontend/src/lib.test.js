import { describe, expect, it } from "vitest";
import { buildTree, citationLabel, splitAnswer, toLines } from "./lib.js";

describe("buildTree", () => {
  it("nests files in folders, folders first", () => {
    const tree = buildTree([
      { path: "README.md" },
      { path: "app/main.py" },
      { path: "app/utils/io.py" },
      { path: "app/config.py" },
    ]);
    expect(tree.map((n) => n.name)).toEqual(["app", "README.md"]);
    const app = tree[0];
    expect(app.children.map((n) => n.name)).toEqual(["utils", "config.py", "main.py"]);
    expect(app.children[0].children[0].path).toBe("app/utils/io.py");
  });
  it("handles an empty list", () => {
    expect(buildTree([])).toEqual([]);
  });
});

describe("splitAnswer", () => {
  it("finds code and citations", () => {
    const pieces = splitAnswer("Use `index_chunks` here [1] and there [2, 3].");
    expect(pieces.map((p) => p.type)).toEqual(["text", "code", "text", "cite", "text", "cite", "text"]);
    expect(pieces[3].numbers).toEqual([1]);
    expect(pieces[5].numbers).toEqual([2, 3]);
  });
  it("leaves plain text alone", () => {
    expect(splitAnswer("nothing special")).toEqual([{ type: "text", value: "nothing special" }]);
  });
  it("does not treat [text] as a citation", () => {
    expect(splitAnswer("a [note] b").every((p) => p.type === "text")).toBe(true);
  });
});

describe("helpers", () => {
  it("labels citations", () => {
    expect(citationLabel({ path: "a.py", start_line: 3, end_line: 9 })).toBe("a.py:3-9");
  });
  it("splits lines like the backend and drops carriage returns", () => {
    expect(toLines("a\r\nb\n")).toEqual(["a", "b", ""]);
  });
});
