import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import { QuotaBar } from "./QuotaBar";

const { getQuota } = vi.hoisted(() => ({
  getQuota: vi.fn(),
}));

vi.mock("../api/modules/quota", () => ({
  getQuota,
}));

describe("QuotaBar", () => {
  beforeEach(() => {
    getQuota.mockReset();
  });

  it("renders the percent for a provisioned instance", async () => {
    getQuota.mockResolvedValue({ granted: 2, remaining: 1.5, percent: 75 });
    renderWithProviders(<QuotaBar />);

    await waitFor(() => {
      expect(screen.getByText("75%")).toBeInTheDocument();
    });
  });

  it("marks low quota in red below 20%", async () => {
    getQuota.mockResolvedValue({ granted: 2, remaining: 0.2, percent: 10 });
    renderWithProviders(<QuotaBar />);

    await waitFor(() => {
      const value = screen.getByText("10%");
      expect(value.className).toContain("quotaBarValueLow");
    });
  });

  it("renders nothing when quota is unavailable", async () => {
    getQuota.mockResolvedValue(null);
    renderWithProviders(<QuotaBar />);

    await waitFor(() => {
      expect(getQuota).toHaveBeenCalled();
    });
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
