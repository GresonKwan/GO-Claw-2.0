import { describe, expect, it } from "vitest";
import { parseQuotaInfo } from "./quota";

describe("parseQuotaInfo", () => {
  it("accepts the optional product-facing integer balance", () => {
    expect(
      parseQuotaInfo({
        granted: 3,
        remaining: 2,
        percent: 67,
        displayRemaining: 10_000_000,
      }),
    ).toEqual({
      granted: 3,
      remaining: 2,
      percent: 67,
      displayRemaining: 10_000_000,
    });
  });

  it("keeps legacy quota responses usable", () => {
    expect(parseQuotaInfo({ granted: 2, remaining: 1, percent: 50 })).toEqual({
      granted: 2,
      remaining: 1,
      percent: 50,
    });
  });

  it.each([-1, 1.5, Number.MAX_SAFE_INTEGER + 1, "5000000"])(
    "omits an invalid display balance: %s",
    (displayRemaining) => {
      expect(
        parseQuotaInfo({
          granted: 2,
          remaining: 1,
          percent: 50,
          displayRemaining,
        }),
      ).toEqual({ granted: 2, remaining: 1, percent: 50 });
    },
  );

  it("rejects a malformed required legacy contract", () => {
    expect(parseQuotaInfo({ remaining: 1, percent: 50 })).toBeNull();
  });
});
