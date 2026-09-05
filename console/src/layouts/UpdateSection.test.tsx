import { readFileSync } from "node:fs";
import { describe, beforeEach, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import { decodeUpdateStatus } from "../api/modules/updates";
import { SidebarBottomDock } from "./SidebarBottomDock";
import { UpdateSection } from "./UpdateSection";

const fixture = decodeUpdateStatus(
  JSON.parse(
    readFileSync(
      "../docs/contracts/v2.1.2/fixtures/update-status.valid.json",
      "utf8",
    ),
  ),
);
const context = {
  status: fixture,
  notifyAvailable: true,
  actionPending: false,
  error: null,
  check: vi.fn(),
  download: vi.fn(),
  install: vi.fn(),
};
vi.mock("../contexts/DesktopUpdateContext", () => ({
  useDesktopUpdate: () => context,
  updateErrorCode: () => "UPDATE_REQUEST_FAILED",
}));
vi.mock("./SidebarSettingsPanel", () => ({ default: () => null }));
vi.mock("./QuotaBar", () => ({ QuotaBar: () => null }));
vi.mock("@agentscope-ai/icons", () => ({
  SparkSettingLine: () => <span>settings</span>,
  SparkMenuExpandLine: () => <span>expand</span>,
  SparkMenuFoldLine: () => <span>fold</span>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeEach(() => {
  context.status = { ...fixture };
  context.notifyAvailable = true;
});
describe("v2 update widgets", () => {
  it("keeps both dots at STAGED and uses one 90 percent progress bar", () => {
    renderWithProviders(
      <>
        <SidebarBottomDock collapsed={false} onCollapsedChange={vi.fn()} />
        <UpdateSection />
      </>,
    );
    expect(screen.getByTestId("settings-update-dot")).toBeInTheDocument();
    expect(screen.getByTestId("check-update-dot")).toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "updates.installNow" }),
    ).toBeInTheDocument();
  });
  it("clears both dots only after engine starts, keeping the same progress area", () => {
    context.status = {
      ...fixture,
      phase: "installing",
      enginePhase: "VERIFYING",
      progressPercent: 97,
      installationStarted: true,
      notifyAvailable: false,
    };
    context.notifyAvailable = false;
    renderWithProviders(
      <>
        <SidebarBottomDock collapsed onCollapsedChange={vi.fn()} />
        <UpdateSection />
      </>,
    );
    expect(screen.queryByTestId("settings-update-dot")).not.toBeInTheDocument();
    expect(screen.queryByTestId("check-update-dot")).not.toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.getByText("97%")).toBeInTheDocument();
  });
});
