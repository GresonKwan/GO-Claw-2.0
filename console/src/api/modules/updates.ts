import { request } from "../request";

export interface UpdateStatus {
  phase:
    | "idle"
    | "checking"
    | "available"
    | "downloading"
    | "downloaded"
    | "installing"
    | "failed";
  currentVersion: string;
  latest: {
    version: string;
    notes: string;
    pubDate: string;
    isNewer: boolean;
  } | null;
  downloaded: number;
  total: number | null;
  error: string;
  enabled: boolean;
}

export interface ReleaseItem {
  version: string;
  notes: string;
  publishedAt: string;
  isCurrent: boolean;
  setupUrl: string;
  signatureUrl: string;
}

async function call<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T | null> {
  try {
    return await request<T>(path, {
      method,
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    return null;
  }
}

export const updatesApi = {
  status: () => call<UpdateStatus>("/updates/status"),
  check: () => call<UpdateStatus>("/updates/check", "POST"),
  download: () => call<UpdateStatus>("/updates/download", "POST"),
  install: () => call<UpdateStatus>("/updates/install", "POST"),
  installVersion: (version: string, url: string, signature: string) =>
    call<UpdateStatus>("/updates/install-version", "POST", {
      version,
      url,
      signature,
    }),
  releases: () => call<{ releases: ReleaseItem[] }>("/updates/releases"),
};
