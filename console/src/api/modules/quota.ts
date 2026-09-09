import { request } from "../request";

export interface QuotaInfo {
  granted: number;
  remaining: number;
  percent: number;
  /** Product-facing integer compute balance. Absent on older servers. */
  displayRemaining?: number;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function parseQuotaInfo(value: unknown): QuotaInfo | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (
    !finiteNumber(raw.granted) ||
    !finiteNumber(raw.remaining) ||
    !finiteNumber(raw.percent)
  ) {
    return null;
  }
  const parsed: QuotaInfo = {
    granted: raw.granted,
    remaining: raw.remaining,
    percent: raw.percent,
  };
  if (
    typeof raw.displayRemaining === "number" &&
    Number.isSafeInteger(raw.displayRemaining) &&
    raw.displayRemaining >= 0
  ) {
    parsed.displayRemaining = raw.displayRemaining;
  }
  return parsed;
}

/**
 * Fetch this portable instance's quota from the backend proxy.
 * Returns null when unavailable (non-portable install, not provisioned,
 * or upstream down) — callers should hide the UI in that case.
 */
export async function getQuota(): Promise<QuotaInfo | null> {
  try {
    return parseQuotaInfo(await request<unknown>("/console/quota"));
  } catch {
    return null;
  }
}
