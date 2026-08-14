import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("i18n", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("always initializes with Simplified Chinese", async () => {
    localStorage.setItem("language", "en");
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("en-US");

    const { default: i18n } = await import("./i18n");

    expect(i18n.language).toBe("zh");
    expect(i18n.options.fallbackLng).toEqual(["zh"]);
    expect(i18n.options.supportedLngs).toContain("zh");
    expect(i18n.options.supportedLngs).not.toContain("en");
  });
});
