import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import Header from "./Header";

const { runtime, getVersion, invoke, openExternalLink, fetchMock } = vi.hoisted(
  () => {
    const runtime = { onDesktop: true, apiVersion: "" };
    return {
      runtime,
      getVersion: vi.fn(() => Promise.resolve({ version: runtime.apiVersion })),
      invoke: vi.fn().mockResolvedValue(undefined),
      openExternalLink: vi.fn(),
      fetchMock: vi.fn(),
    };
  },
);

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
  isDesktopApp: () => runtime.onDesktop,
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke }));

vi.mock("../utils/openExternalLink", () => ({ openExternalLink }));

vi.mock("../plugins/registry/Slot", () => ({
  Slot: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@agentscope-ai/design", () => ({
  Button: ({
    children,
    onClick,
  }: {
    children?: React.ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
  Modal: ({
    open,
    children,
    footer,
  }: {
    open?: boolean;
    children?: React.ReactNode;
    footer?: React.ReactNode;
  }) =>
    open ? (
      <div role="dialog">
        {children}
        {footer}
      </div>
    ) : null,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "header.resources": "文档资料",
        "header.github": "GitHub",
        "sidebar.settings.language": "语言",
        "common.close": "关闭",
        "sidebar.updateModal.viewReleases": "查看更新详情",
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
  beforeEach(() => {
    runtime.onDesktop = true;
    runtime.apiVersion = "";
    getVersion.mockImplementation(() =>
      Promise.resolve({ version: runtime.apiVersion }),
    );
    invoke.mockResolvedValue(undefined);
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      json: vi.fn().mockResolvedValue({ releases: {} }),
    });
    openExternalLink.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    localStorage.clear();
  });

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

  it("shows local GO CLAW update guidance and opens release details on web", async () => {
    const user = userEvent.setup();
    runtime.onDesktop = false;
    runtime.apiVersion = "1.0.0";
    fetchMock.mockResolvedValue({
      json: vi.fn().mockResolvedValue({
        releases: {
          "2.0.0": [{ upload_time_iso_8601: "2020-01-01T00:00:00Z" }],
        },
      }),
    });
    renderHeader();

    const versionBadge = await screen.findByText("v1.0.0");
    await waitFor(() =>
      expect(document.querySelector(".ant-badge-dot")).toBeInTheDocument(),
    );
    await user.click(versionBadge);

    expect(
      screen.getByRole("heading", { name: "如何更新 GO CLAW" }),
    ).toBeInTheDocument();
    expect(screen.getByText("pip install -U qwenpaw")).toBeInTheDocument();
    const releaseDetails = screen.getByRole("button", {
      name: "查看更新详情",
    });
    await user.click(releaseDetails);

    expect(openExternalLink).toHaveBeenCalledWith(
      "https://qwenpaw.agentscope.io/release-notes?lang=zh",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://pypi.org/pypi/qwenpaw/json",
    );
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("faq.")),
    ).toBe(false);
  });

  it("opens desktop DevTools after eight rapid logo clicks", async () => {
    const user = userEvent.setup();
    renderHeader();
    const logo = screen.getByTestId("go-claw-header-logo");

    for (let click = 0; click < 8; click += 1) {
      await user.click(logo);
    }

    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke).toHaveBeenCalledWith("open_devtools");
  });
});
