import { buildAuthHeaders } from "../authHeaders";
import { getApiUrl } from "../config";

export type DeliverableKind =
  | "document"
  | "image"
  | "video"
  | "audio"
  | "archive"
  | "code"
  | "other";

export interface DeliverableItem {
  id: string;
  turnId: string;
  name: string;
  kind: DeliverableKind;
  mimeType: string;
  sizeBytes: number;
  exists: boolean;
  directOpenAllowed: boolean;
  previewAllowed: boolean;
  previewKind: "image" | "video" | null;
  createdAt: string;
}

export interface DeliverablesEnvelope {
  schemaVersion: 1;
  agentId: string;
  chatId: string;
  turnId: string;
  responseId: string;
  revision: number;
  status: "ready" | "unavailable";
  items: DeliverableItem[];
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    ...init,
    headers: {
      ...buildAuthHeaders(),
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.code || `HTTP_${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const deliverablesApi = {
  query: (chatId: string, responseIds: string[], signal?: AbortSignal) =>
    json<{ schemaVersion: 1; turns: DeliverablesEnvelope[] }>(
      "/console/deliverables/query",
      {
        method: "POST",
        signal,
        body: JSON.stringify({ chatId, responseIds }),
      },
    ),
  open: (id: string, action: "open" | "reveal") =>
    json<{ ok: true; action: "open" | "reveal" }>(
      `/console/deliverables/${encodeURIComponent(id)}/open`,
      { method: "POST", body: JSON.stringify({ action }) },
    ),
  mediaTicket: (id: string) =>
    json<{ ticket: string; expiresAt: number }>(
      `/console/deliverables/${encodeURIComponent(id)}/media-ticket`,
      { method: "POST" },
    ),
  mediaUrl: (id: string, ticket: string, kind: "thumbnail" | "content") =>
    getApiUrl(
      `/console/deliverables/${encodeURIComponent(
        id,
      )}/${kind}?ticket=${encodeURIComponent(ticket)}`,
    ),
};
