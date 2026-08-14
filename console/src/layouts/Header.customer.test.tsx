import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import Header from "./Header";

const { getVersion, invoke } = vi.hoisted(() => ({
  getVersion: vi.fn(() => new Promise(() => {})),
  invoke: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../api", () => ({
  default: { getVersion },
}));

vi.mock("../contexts/DesktopUpdateContext", () => ({
  useDesktopUpdate: () => ({
    phase: "idle",
    isBackground: false,
    hasUpdate: false,
    supportsLaterInstall: false,
    version: "",
    body: "",
    downloaded: 0,
    total: null,
    throughputBps: 0,
    error: null,
    startInstall: vi.fn(),
    startBackgroundDownload: vi.fn(),
    installDownloaded: vi.fn(),
    retry: vi.fn(),
    dismissFailure: vi.fn(),
  }),
}));

vi.mock("../tauri/backendRuntime", () => ({
  isDesktopApp: () => true,
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke }));

vi.mock("../plugins/registry/Slot", () => ({
  Slot: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "header.resources": "文档资料",
        "header.github": "GitHub",
        "sidebar.settings.language": "语言",
      })[key] ?? key,
    i18n: { language: "zh", resolvedLanguage: "zh", changeLanguage: vi.fn() },
  }),
}));

function DarkThemeButton() {
  const { setThemeMode } = useTheme();
  return <button onClick={() => setThemeMode("dark")}>dark theme</button>;
}

function renderHeader() {
  localStorage.setItem("qwenpaw-theme", "light");
  return renderWithProviders(
    <ThemeProvider>
      <DarkThemeButton />
      <Header />
    </ThemeProvider>,
  );
}

describe("customer Header", () => {
  it("shows the GO CLAW logo without legacy resource navigation", () => {
    renderHeader();

    expect(screen.getByAltText("GO CLAW")).toHaveAttribute(
      "src",
      "/go-claw-horizontal.svg",
    );
    expect(screen.getByTestId("go-claw-header-logo")).toBeInTheDocument();
    expect(screen.queryByText("文档资料")).not.toBeInTheDocument();
    expect(screen.queryByText("GitHub")).not.toBeInTheDocument();
    expect(screen.queryByTitle("语言")).not.toBeInTheDocument();
    expect(screen.queryByTitle("文档资料")).not.toBeInTheDocument();
  });

  it("switches to the white GO CLAW logo in dark theme", async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByRole("button", { name: "dark theme" }));

    expect(screen.getByAltText("GO CLAW")).toHaveAttribute(
      "src",
      "/go-claw-horizontal-white.svg",
    );
  });
});
