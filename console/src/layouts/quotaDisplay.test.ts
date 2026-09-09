import { describe, expect, it } from "vitest";
import {
  formatComputeBalance,
  formatExactComputeBalance,
} from "./quotaDisplay";

describe("quota display formatting", () => {
  it.each([
    [0, "0"],
    [9_999, "9,999"],
    [10_000, "1万"],
    [52_800_000, "5,280万"],
    [105_000_000, "1.1亿"],
  ])("formats %s as %s", (value, expected) => {
    expect(formatComputeBalance(value)).toBe(expected);
  });

  it("keeps the exact grouped balance available", () => {
    expect(formatExactComputeBalance(52_800_000)).toBe("52,800,000");
  });
});
