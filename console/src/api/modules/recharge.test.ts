import { beforeEach, describe, expect, it, vi } from "vitest";
import { rechargeApi } from "./recharge";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request }));

describe("recharge API", () => {
  beforeEach(() => request.mockReset());

  it("submits only fen and the accepted terms version", async () => {
    request.mockResolvedValue({ orderId: "test" });
    await rechargeApi.createOrder(101, "terms-v1", "idem_key_1234567890");
    expect(request).toHaveBeenCalledWith("/console/recharge/orders", {
      method: "POST",
      headers: { "Idempotency-Key": "idem_key_1234567890" },
      body: JSON.stringify({
        amountFen: 101,
        acceptedTermsVersion: "terms-v1",
      }),
      timeout: 20_000,
    });
    const serialized = JSON.stringify(request.mock.calls[0]);
    expect(serialized.toLowerCase()).not.toContain("newapi");
    expect(serialized).not.toContain("computeUnits");
  });
});
