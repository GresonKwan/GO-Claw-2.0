/**
 * Tests for layouts/constants.
 *
 * Covers:
 * - Customer-facing URL constants
 * - ONE_HOUR_MS value
 * - getWebsiteLang()
 * - getReleaseNotesUrl()
 * - isStableVersion()
 * - compareVersions()
 * - Customer update copy
 */
import { describe, it, expect } from "vitest";
import {
  PYPI_URL,
  ONE_HOUR_MS,
  getWebsiteLang,
  getReleaseNotesUrl,
  isStableVersion,
  compareVersions,
  UPDATE_MD,
} from "./constants";

describe("URL constants", () => {
  it("PYPI_URL points to qwenpaw json endpoint", () => {
    expect(PYPI_URL).toBe("https://pypi.org/pypi/qwenpaw/json");
  });
});

describe("ONE_HOUR_MS", () => {
  it("equals 3600000 ms", () => {
    expect(ONE_HOUR_MS).toBe(60 * 60 * 1000);
  });
});

describe("getWebsiteLang", () => {
  it.each([
    ["zh", "zh"],
    ["zh-CN", "zh"],
    ["zh-TW", "zh"],
    ["en", "en"],
    ["en-US", "en"],
    ["ja", "en"],
    ["ru", "en"],
  ])("returns %s for input %s", (input, expected) => {
    expect(getWebsiteLang(input)).toBe(expected);
  });
});

describe("getReleaseNotesUrl", () => {
  it("includes lang param", () => {
    const url = getReleaseNotesUrl("zh");
    expect(url).toContain("lang=zh");
    expect(url).toContain("/release-notes");
  });
});

describe("isStableVersion", () => {
  it.each([
    ["1.0.0", true],
    ["2.3.4", true],
    ["1.0.0.post1", true],
    ["1.0.0a1", false],
    ["1.0.0beta2", false],
    ["2.0rc1", false],
    ["3.0.0dev1", false],
    ["1.0.0c3", false],
  ])("isStableVersion(%s) → %s", (version, expected) => {
    expect(isStableVersion(version)).toBe(expected);
  });
});

describe("compareVersions", () => {
  it.each([
    ["1.0.0", "2.0.0", -1],
    ["2.0.0", "1.0.0", 1],
    ["1.0.0", "1.0.0", 0],
    ["1.0.0", "1.0.1", -1],
    ["1.0.1", "1.0.0", 1],
    ["1.0.0a1", "1.0.0", -1],
    ["1.0.0", "1.0.0a1", 1],
    ["1.0.0b1", "1.0.0", -1],
    ["1.0.0rc1", "1.0.0", -1],
    ["1.0.0a1", "1.0.0b1", -1],
    ["1.0.0b1", "1.0.0rc1", -1],
    ["1.0.0", "1.0.0.post1", -1],
    ["1.0.0.post1", "1.0.0.post2", -1],
  ] as [string, string, number][])(
    "compareVersions(%s, %s) → %s",
    (a, b, expected) => {
      const result = compareVersions(a, b);
      expect(Math.sign(result)).toBe(expected);
    },
  );
});

describe("UPDATE_MD", () => {
  it("is a single Chinese GO CLAW update guide with supported commands", () => {
    expect(typeof UPDATE_MD).toBe("string");
    expect(UPDATE_MD).toContain("GO CLAW");
    expect(UPDATE_MD).toContain("pip install -U qwenpaw");
    expect(UPDATE_MD).toContain("uv tool upgrade qwenpaw");
  });
});
