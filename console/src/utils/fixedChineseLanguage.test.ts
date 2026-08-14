import type { i18n, TFunction } from "i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { synchronizeFixedChineseLanguage } from "./fixedChineseLanguage";

const translationFunction = vi.fn() as unknown as TFunction;

describe("synchronizeFixedChineseLanguage", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it("removes the legacy language cache and synchronizes Chinese", async () => {
    localStorage.setItem("language", "en");
    const changeLanguage = vi
      .fn<i18n["changeLanguage"]>()
      .mockResolvedValue(translationFunction);
    const updateLanguage = vi.fn().mockResolvedValue(undefined);

    await synchronizeFixedChineseLanguage(
      { language: "zh", changeLanguage },
      updateLanguage,
    );

    expect(localStorage.getItem("language")).toBeNull();
    expect(changeLanguage).not.toHaveBeenCalled();
    expect(updateLanguage).toHaveBeenCalledWith("zh");
  });

  it("changes a non-Chinese language before synchronizing the backend", async () => {
    const calls: string[] = [];
    const changeLanguage = vi.fn<i18n["changeLanguage"]>(async (language) => {
      calls.push(`change:${language}`);
      return translationFunction;
    });
    const updateLanguage = vi.fn(async (language: string) => {
      calls.push(`update:${language}`);
    });

    await synchronizeFixedChineseLanguage(
      { language: "en", changeLanguage },
      updateLanguage,
    );

    expect(changeLanguage).toHaveBeenCalledWith("zh");
    expect(calls).toEqual(["change:zh", "update:zh"]);
  });

  it("reports backend errors without rejecting", async () => {
    const error = new Error("backend unavailable");
    const updateLanguage = vi.fn().mockRejectedValue(error);
    const reportError = vi.fn();

    await expect(
      synchronizeFixedChineseLanguage(
        {
          language: "zh",
          changeLanguage: vi
            .fn<i18n["changeLanguage"]>()
            .mockResolvedValue(translationFunction),
        },
        updateLanguage,
        reportError,
      ),
    ).resolves.toBeUndefined();
    expect(reportError).toHaveBeenCalledWith(expect.any(String), error);
  });
});
