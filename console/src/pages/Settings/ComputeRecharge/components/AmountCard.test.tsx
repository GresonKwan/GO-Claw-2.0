import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RechargeConfig } from "../../../../api/modules/recharge";
import { AmountCard } from "./AmountCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const config: RechargeConfig = {
  enabled: true,
  currency: "CNY",
  pricingVersion: "cny-v1",
  computeUnitsPerFen: 50000,
  displayRate: "￥1对应500万算力",
  minAmountFen: 100,
  maxAmountFen: 10000000,
  amountStepFen: 1,
  dailyLimitFen: 10000000,
  presetsFen: [1000, 5000, 10000, 20000],
  termsVersion: "2026-09-v1",
  refundMode: "CUSTOMER_SERVICE",
  customerServiceUrl: null,
  invoicesEnabled: false,
};

describe("AmountCard", () => {
  it("uses whole-yuan input and omits the operational policy hint", () => {
    render(
      <AmountCard
        config={config}
        amountFen={1000}
        submitting={false}
        disabled={false}
        onAmountChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    const input = screen.getByRole("spinbutton", {
      name: "computeRecharge.customAmount",
    });
    expect(input).toHaveValue("10");
    expect(input).toHaveAttribute("step", "1");
    expect(
      screen.queryByText("computeRecharge.dailyLimit"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("computeRecharge.refundAndInvoice"),
    ).not.toBeInTheDocument();
  });
});
