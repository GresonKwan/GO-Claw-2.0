import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import zh from "@/locales/zh.json";
import { SkillMarketBanner } from "./SkillMarketBanner";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => zh.skills[key.split(".")[1] as keyof typeof zh.skills],
  }),
}));

describe("SkillMarketBanner", () => {
  it("renders the approved copy and an accessible market entry", async () => {
    const onBrowse = vi.fn();
    render(<SkillMarketBanner onBrowse={onBrowse} />);
    expect(
      screen.getByRole("region", { name: "从技能中获得专业能力" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "从技能中获得专业能力" }),
    ).toBeVisible();
    expect(screen.getByText("从11万个技能中，找到效率最优解")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "浏览技能" }));
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });

  it("can be reached and activated by keyboard", async () => {
    const onBrowse = vi.fn();
    render(<SkillMarketBanner onBrowse={onBrowse} />);
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "浏览技能" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });
});
