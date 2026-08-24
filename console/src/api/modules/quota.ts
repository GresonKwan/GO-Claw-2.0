import { request } from "../request";

export interface QuotaInfo {
  granted: number;
  remaining: number;
  percent: number;
}

/**
 * Fetch this portable instance's quota from the backend proxy.
 * Returns null when unavailable (non-portable install, not provisioned,
 * or upstream down) — callers should hide the UI in that case.
 */
export async function getQuota(): Promise<QuotaInfo | null> {
  try {
    return await request<QuotaInfo>("/console/quota");
  } catch {
    return null;
  }
}
