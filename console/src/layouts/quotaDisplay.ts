export const LOW_COMPUTE_THRESHOLD = 5_000_000;

const compactFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 1,
});
const integerFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 0,
});

/** Compact balance without hiding the exact value from the tooltip/aria label. */
export function formatComputeBalance(value: number): string {
  if (!Number.isSafeInteger(value) || value < 0) return "--";
  if (value < 10_000) return integerFormatter.format(value);
  if (value < 100_000_000) {
    return `${compactFormatter.format(value / 10_000)}万`;
  }
  return `${compactFormatter.format(value / 100_000_000)}亿`;
}

export function formatExactComputeBalance(value: number): string {
  if (!Number.isSafeInteger(value) || value < 0) return "--";
  return integerFormatter.format(value);
}
