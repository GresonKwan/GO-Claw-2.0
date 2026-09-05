import { request } from "../request";
import { getApiUrl } from "../config";
import { buildAuthHeaders } from "../authHeaders";

export const enginePhases = [
  "IDLE",
  "CHECKING",
  "AVAILABLE",
  "PLANNING",
  "DOWNLOADING",
  "STAGED",
  "SWITCH_PENDING",
  "VERIFYING",
  "COMMITTED",
  "FAILED",
  "ROLLING_BACK",
  "ROLLED_BACK",
  "BLOCKED",
] as const;
export type EnginePhase = (typeof enginePhases)[number];
export interface UpdateStatus {
  schemaVersion?: 2;
  revision?: number;
  enginePhase?: EnginePhase;
  progressPercent?: number | null;
  installationStarted?: boolean;
  notifyAvailable?: boolean;
  transactionId?: string | null;
  targetManifestSha256?: string | null;
  activeSlot?: string;
  targetSlot?: string | null;
  changedComponents?: string[];
  downloadBytes?: number;
  fullBytes?: number;
  estimateOnly?: boolean;
  failure?: { code: string; stage: string; retryable: boolean } | null;
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

const phases = [
  "idle",
  "checking",
  "available",
  "downloading",
  "downloaded",
  "installing",
  "failed",
];
const bytes = (value: unknown): value is number =>
  Number.isSafeInteger(value) && (value as number) >= 0;
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export function decodeUpdateStatus(value: unknown): UpdateStatus {
  if (
    !object(value) ||
    (value.schemaVersion !== undefined && value.schemaVersion !== 2)
  )
    throw new Error("UNSUPPORTED_UPDATE_SCHEMA");
  if (
    !phases.includes(String(value.phase)) ||
    typeof value.currentVersion !== "string" ||
    typeof value.enabled !== "boolean" ||
    typeof value.error !== "string" ||
    !bytes(value.downloaded) ||
    (value.total !== null && !bytes(value.total))
  )
    throw new Error("INVALID_UPDATE_STATUS");
  if (
    value.latest !== null &&
    (!object(value.latest) ||
      typeof value.latest.version !== "string" ||
      typeof value.latest.isNewer !== "boolean" ||
      typeof value.latest.notes !== "string" ||
      typeof value.latest.pubDate !== "string")
  )
    throw new Error("INVALID_UPDATE_STATUS");
  if (value.schemaVersion === 2) {
    if (
      !bytes(value.revision) ||
      !enginePhases.includes(value.enginePhase as EnginePhase) ||
      typeof value.installationStarted !== "boolean" ||
      typeof value.notifyAvailable !== "boolean" ||
      !bytes(value.downloadBytes) ||
      !bytes(value.fullBytes) ||
      (value.progressPercent !== null &&
        (typeof value.progressPercent !== "number" ||
          !Number.isFinite(value.progressPercent) ||
          value.progressPercent < 0 ||
          value.progressPercent > 100)) ||
      (value.targetManifestSha256 !== null &&
        (typeof value.targetManifestSha256 !== "string" ||
          !/^[0-9a-f]{64}$/.test(value.targetManifestSha256))) ||
      (value.transactionId !== null &&
        (typeof value.transactionId !== "string" ||
          !/^[0-9a-f-]{36}$/.test(value.transactionId)))
    )
      throw new Error("INVALID_UPDATE_STATUS");
  }
  return value as unknown as UpdateStatus;
}

async function statusCall(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<UpdateStatus | null> {
  try {
    return decodeUpdateStatus(
      await request<unknown>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    );
  } catch (error) {
    if (error instanceof Error && error.message.includes("updates_unavailable"))
      return null;
    throw error;
  }
}

/** Authenticated fetch stream: native EventSource cannot carry our login header. */
export async function watchUpdateStatus(
  signal: AbortSignal,
  onStatus: (status: UpdateStatus) => void,
  revision?: number,
) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) abort();
  let timer: ReturnType<typeof setTimeout>;
  const heartbeat = () => {
    clearTimeout(timer);
    timer = setTimeout(abort, 45_000);
  };
  heartbeat();
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const response = await fetch(getApiUrl("/updates/events"), {
      headers: {
        ...buildAuthHeaders(),
        Accept: "text/event-stream",
        ...(revision === undefined
          ? {}
          : { "Last-Event-ID": String(revision) }),
      },
      signal: controller.signal,
    });
    if (
      !response.ok ||
      !response.headers.get("content-type")?.includes("text/event-stream") ||
      !response.body
    )
      throw new Error("UPDATE_STREAM_UNAVAILABLE");
    reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let buffer = "";
    while (!controller.signal.aborted) {
      const { value, done } = await reader.read();
      if (done) throw new Error("UPDATE_STREAM_CLOSED");
      heartbeat();
      buffer += decoder.decode(value, { stream: true });
      if (buffer.length > 1024 * 1024)
        throw new Error("UPDATE_STREAM_TOO_LARGE");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        if (!frame.split("\n").includes("event: update.status")) continue;
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        onStatus(decodeUpdateStatus(JSON.parse(data)));
      }
    }
  } finally {
    clearTimeout(timer!);
    controller.abort();
    await reader?.cancel().catch(() => {});
    reader?.releaseLock();
    signal.removeEventListener("abort", abort);
  }
}

export const updatesApi = {
  status: () => statusCall("/updates/status"),
  check: () => statusCall("/updates/check", "POST"),
  download: (target?: UpdateStatus) =>
    statusCall(
      "/updates/download",
      "POST",
      target?.schemaVersion === 2
        ? {
            targetVersion: target.latest?.version,
            targetManifestSha256: target.targetManifestSha256,
          }
        : undefined,
    ),
  install: (target?: UpdateStatus) =>
    statusCall(
      "/updates/install",
      "POST",
      target?.schemaVersion === 2
        ? {
            transactionId: target.transactionId,
            targetManifestSha256: target.targetManifestSha256,
          }
        : undefined,
    ),
  installVersion: (version: string, url: string, signature: string) =>
    statusCall("/updates/install-version", "POST", { version, url, signature }),
  releases: () => request<{ releases: ReleaseItem[] }>("/updates/releases"),
};
