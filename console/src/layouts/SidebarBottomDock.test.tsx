import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import { SidebarBottomDock } from "./SidebarBottomDock";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("./QuotaBar", () => ({
  QuotaBar: ({ collapsed }: { collapsed?: boolean }) => (
    <div data-testid="quota-control">{collapsed ? "ring" : "bar"}</div>
  ),
}));
vi.mock("./SidebarSettingsPanel", () => ({
  default: () => <div>settings</div>,
}));
vi.mock("@agentscope-ai/icons", () => ({
  SparkSettingLine: () => <span>settings-icon</span>,
  SparkMenuExpandLine: () => <span>expand-icon</span>,
  SparkMenuFoldLine: () => <span>fold-icon</span>,
}));

describe("SidebarBottomDock", () => {
  it.each([false, true])(
    "keeps quota, settings and collapse controls in one ordered dock (collapsed=%s)",
    (collapsed) => {
      renderWithProviders(
        <SidebarBottomDock collapsed={collapsed} onCollapsedChange={vi.fn()} />,
      );
      const dock = screen.getByTestId("sidebar-bottom-dock");
      expect(within(dock).getByTestId("quota-control")).toHaveTextContent(
        collapsed ? "ring" : "bar",
      );
      expect(
        within(dock).getByRole("button", { name: "nav.settings" }),
      ).toBeInTheDocument();
      expect(
        within(dock).getByRole("button", {
          name: collapsed ? "sidebar.expand" : "sidebar.collapse",
        }),
      ).toBeInTheDocument();

      const ordered = Array.from(dock.querySelectorAll("[data-dock-order]"));
      expect(
        ordered.map((node) => node.getAttribute("data-dock-order")),
      ).toEqual(["quota", "actions"]);
    },
  );
});
