import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import SidebarSettingsPanel from "./SidebarSettingsPanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: {
      language: "zh",
      resolvedLanguage: "zh",
      changeLanguage: vi.fn(),
    },
  }),
}));

vi.mock("../contexts/ThemeContext", () => ({
  useTheme: () => ({ themeMode: "light", setThemeMode: vi.fn() }),
}));

vi.mock("../stores/sidebarModeStore", () => ({
  useSidebarModeStore: () => ({ mode: "full", toggleMode: vi.fn() }),
}));

vi.mock("../tauri/backendRuntime", () => ({ isTauriRuntime: () => false }));
vi.mock("./UpdateSection", () => ({
  UpdateSection: () => <div>版本与更新</div>,
}));
vi.mock("@agentscope-ai/icons", () => ({
  SparkSunLine: () => <span>sun</span>,
  SparkMoonLine: () => <span>moon</span>,
  SparkFullscreenLine: () => <span>full</span>,
  SparkExitFullscreenLine: () => <span>simple</span>,
}));

describe("SidebarSettingsPanel", () => {
  it("keeps customer settings but has no language controls", () => {
    renderWithProviders(<SidebarSettingsPanel />);
    expect(screen.queryByText("Language")).not.toBeInTheDocument();
    expect(screen.queryByTitle("English")).not.toBeInTheDocument();
    expect(screen.getByText("Theme")).toBeInTheDocument();
    expect(screen.getByText("版本与更新")).toBeInTheDocument();
  });
});
