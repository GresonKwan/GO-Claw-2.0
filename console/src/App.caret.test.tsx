import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("browser caret policy", () => {
  it("hides static-text carets and restores editable carets", () => {
    const source = readFileSync(`${process.cwd()}/src/App.tsx`, "utf8");
    expect(source).toContain(`#root,
#root * {
  caret-color: transparent;
}`);
    expect(source).toContain(`#root input,
#root textarea,
#root [contenteditable]:not([contenteditable="false"]),
#root .monaco-editor textarea,
#root .cm-editor [contenteditable]:not([contenteditable="false"]) {
  caret-color: auto;
}`);
    expect(source).not.toContain("user-select: none");
  });
});
