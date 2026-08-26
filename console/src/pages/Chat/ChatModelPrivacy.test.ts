import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("customer chat model privacy", () => {
  it("has no legacy direct-switch or raw alternative model UI", () => {
    const source = readFileSync(
      `${process.cwd()}/src/pages/Chat/index.tsx`,
      "utf8",
    );
    expect(source).not.toContain("setActiveLlm");
    expect(source).not.toContain("rateLimitAlternatives");
    expect(source).not.toContain("alt.model_name");
  });
});
