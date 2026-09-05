import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SkillsPage from "./index";

const state = vi.hoisted(() => ({
  skills: [] as unknown[],
  visibleSkills: [],
  sortedSkills: [],
  selectedSkills: new Set<string>(),
  loading: false,
  refreshSkills: vi.fn(),
}));
vi.mock("./useSkillsPage", () => ({ useSkillsPage: () => state }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@/components/PageHeader", () => ({
  PageHeader: ({ extra }: { extra: React.ReactNode }) => (
    <header>{extra}</header>
  ),
}));
vi.mock("../../Settings/Market/MarketPanel", () => ({
  MarketPanel: () => <div data-testid="market" />,
}));
vi.mock("./components", async () => ({
  SkillMarketBanner: (await import("./components/SkillMarketBanner"))
    .SkillMarketBanner,
  HeaderActions: ({ onBrowseMarket }: { onBrowseMarket: () => void }) => (
    <button onClick={onBrowseMarket}>existing-market-entry</button>
  ),
  SkillsToolbar: () => <div data-testid="toolbar" />,
  ImportHubModal: () => null,
  PoolTransferModal: () => null,
  SkillDrawer: () => null,
  SkillCard: () => null,
  SkillListItem: () => null,
  getSkillVisual: () => null,
}));

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>;
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/skills?keep=value"]}>
      <SkillsPage />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("Skills page market banner integration", () => {
  beforeEach(() => {
    state.skills = [];
    state.loading = false;
    state.refreshSkills.mockClear();
  });

  it.each(["empty", "populated", "loading"])(
    "is present on the %s skills page",
    (mode) => {
      state.skills = mode === "populated" ? [{}] : [];
      state.loading = mode === "loading";
      const { container } = mount();
      const banner = screen.getByRole("region", {
        name: "skills.marketBannerTitle",
      });
      expect(banner).toBeVisible();
      expect(container.querySelector("header")?.nextElementSibling).toBe(
        banner,
      );
      expect(
        screen.getByRole("button", { name: "existing-market-entry" }),
      ).toBeVisible();
      if (mode === "populated") {
        expect(
          banner.compareDocumentPosition(screen.getByTestId("toolbar")) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
      }
    },
  );

  it("reuses the market query route, preserves other parameters and refreshes on return", async () => {
    mount();
    await userEvent.click(
      screen.getByRole("button", { name: "skills.marketBannerBrowse" }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?keep=value&view=market",
    );
    expect(screen.getByTestId("market")).toBeVisible();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /common\.back/ }));
    expect(screen.getByTestId("location")).toHaveTextContent("?keep=value");
    expect(state.refreshSkills).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("region")).toBeVisible();
  });
});
