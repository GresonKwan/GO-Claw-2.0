import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import { QuotaBar } from "./QuotaBar";

const { getQuota } = vi.hoisted(() => ({
  getQuota: vi.fn(),
}));

vi.mock("../api/modules/quota", () => ({ getQuota }));

describe("QuotaBar", () => {
  beforeEach(() => getQuota.mockReset());

  it("renders the product-facing balance instead of a percentage", async () => {
    getQuota.mockResolvedValue({
      granted: 2,
      remaining: 1.5,
      percent: 75,
      displayRemaining: 52_800_000,
    });
    renderWithProviders(<QuotaBar />);

    expect(await screen.findByText("5,280万")).toBeInTheDocument();
    expect(screen.queryByText("75%")).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("marks a display balance below five million as low", async () => {
    getQuota.mockResolvedValue({
      granted: 2,
      remaining: 0.2,
      percent: 10,
      displayRemaining: 4_999_999,
    });
    renderWithProviders(<QuotaBar />);

    const value = await screen.findByText("500万");
    expect(value.className).toContain("quotaBarValueLow");
  });

  it("renders a compact accessible balance control when collapsed", async () => {
    getQuota.mockResolvedValue({
      granted: 2,
      remaining: 1,
      percent: 50,
      displayRemaining: 10_000_000,
    });
    renderWithProviders(<QuotaBar collapsed />);

    await waitFor(() => expect(getQuota).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button").getAttribute("aria-label")).toContain(
      "10,000,000",
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("keeps an old server response usable through percent compatibility", async () => {
    getQuota.mockResolvedValue({ granted: 2, remaining: 1, percent: 50 });
    renderWithProviders(<QuotaBar />);

    expect(await screen.findByText("50%")).toBeInTheDocument();
  });

  it("shows a stable unavailable state instead of removing the dock", async () => {
    getQuota.mockResolvedValue(null);
    renderWithProviders(<QuotaBar />);

    expect(await screen.findByText("--")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("refreshes once and announces only the credited delta", async () => {
    getQuota
      .mockResolvedValueOnce({
        granted: 2,
        remaining: 1,
        percent: 50,
        displayRemaining: 10_000_000,
      })
      .mockResolvedValueOnce({
        granted: 3,
        remaining: 2,
        percent: 67,
        displayRemaining: 15_000_000,
      });
    renderWithProviders(<QuotaBar />);
    await waitFor(() => expect(getQuota).toHaveBeenCalledTimes(1));

    window.dispatchEvent(new Event("go-claw:quota-updated"));
    await waitFor(() => expect(getQuota).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("status")).toHaveTextContent("500万");
  });
});
