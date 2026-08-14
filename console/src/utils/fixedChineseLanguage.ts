import type { i18n } from "i18next";
import { languageApi } from "../api/modules/language";

export async function synchronizeFixedChineseLanguage(
  languageEngine: Pick<i18n, "language" | "changeLanguage">,
  updateLanguage: (
    language: string,
  ) => Promise<unknown> = languageApi.updateLanguage,
  reportError: (message: string, error: unknown) => void = console.error,
): Promise<void> {
  localStorage.removeItem("language");

  if (languageEngine.language !== "zh") {
    try {
      await languageEngine.changeLanguage("zh");
    } catch (error) {
      reportError("Failed to switch language to Chinese:", error);
    }
  }

  try {
    await updateLanguage("zh");
  } catch (error) {
    reportError("Failed to synchronize fixed Chinese language:", error);
  }
}
