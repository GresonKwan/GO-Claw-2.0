import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export const BACKEND_READY_EVENT = "go-claw-client-backend-ready";

export type ClientPhase =
  | "processStarting"
  | "bootstrapCreating"
  | "bootstrapReady"
  | "backendReady"
  | "consoleNavigating"
  | "consoleReady"
  | "desktopActive"
  | "browserFallback"
  | "fatalStartup";

export type BrowserFallbackReason =
  | "explicitBrowserMode"
  | "webviewBuildFailed"
  | "bootstrapReadyTimeout"
  | "consoleNavigationFailed"
  | "consoleReadyTimeout";

export interface ClientReadinessSnapshot {
  schemaVersion: 1;
  launchId: number;
  phase: ClientPhase;
  backendPort: number | null;
  consoleUrl: string | null;
  fallbackReason: BrowserFallbackReason | null;
  fatalReason: "backendStartupFailed" | null;
  browserOpened: boolean;
}

export interface ClientBackendReadyPayload {
  schemaVersion: 1;
  launchId: number;
  port: number;
  consoleUrl: string;
}

const CLIENT_PHASES = new Set<ClientPhase>([
  "processStarting",
  "bootstrapCreating",
  "bootstrapReady",
  "backendReady",
  "consoleNavigating",
  "consoleReady",
  "desktopActive",
  "browserFallback",
  "fatalStartup",
]);

const FALLBACK_REASONS = new Set<BrowserFallbackReason>([
  "explicitBrowserMode",
  "webviewBuildFailed",
  "bootstrapReadyTimeout",
  "consoleNavigationFailed",
  "consoleReadyTimeout",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return (
    actual.length === expected.length &&
    actual.every((key, index) => key === expected[index])
  );
}

function isNullablePort(value: unknown): value is number | null {
  return (
    value === null ||
    (typeof value === "number" &&
      Number.isInteger(value) &&
      value > 0 &&
      value <= 65535)
  );
}

export function parseClientReadinessSnapshot(
  value: unknown,
): ClientReadinessSnapshot {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "schemaVersion",
      "launchId",
      "phase",
      "backendPort",
      "consoleUrl",
      "fallbackReason",
      "fatalReason",
      "browserOpened",
    ]) ||
    value.schemaVersion !== 1 ||
    typeof value.launchId !== "number" ||
    !Number.isSafeInteger(value.launchId) ||
    value.launchId < 1 ||
    typeof value.phase !== "string" ||
    !CLIENT_PHASES.has(value.phase as ClientPhase) ||
    !isNullablePort(value.backendPort) ||
    !(value.consoleUrl === null || typeof value.consoleUrl === "string") ||
    !(
      value.fallbackReason === null ||
      (typeof value.fallbackReason === "string" &&
        FALLBACK_REASONS.has(value.fallbackReason as BrowserFallbackReason))
    ) ||
    !(
      value.fatalReason === null || value.fatalReason === "backendStartupFailed"
    ) ||
    typeof value.browserOpened !== "boolean"
  ) {
    throw new Error("invalid client readiness snapshot");
  }
  return value as unknown as ClientReadinessSnapshot;
}

function parseBackendReadyPayload(value: unknown): ClientBackendReadyPayload {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["schemaVersion", "launchId", "port", "consoleUrl"]) ||
    value.schemaVersion !== 1 ||
    typeof value.launchId !== "number" ||
    !Number.isSafeInteger(value.launchId) ||
    value.launchId < 1 ||
    !isNullablePort(value.port) ||
    value.port === null ||
    typeof value.consoleUrl !== "string"
  ) {
    throw new Error("invalid backend-ready event");
  }
  return value as unknown as ClientBackendReadyPayload;
}

export async function clientReadinessSnapshot(): Promise<ClientReadinessSnapshot> {
  return parseClientReadinessSnapshot(
    await invoke<unknown>("client_readiness_snapshot"),
  );
}

async function invokeTransition(
  command: string,
  launchId: number,
): Promise<ClientReadinessSnapshot> {
  return parseClientReadinessSnapshot(
    await invoke<unknown>(command, { launchId }),
  );
}

export function clientBootstrapReady(
  launchId: number,
): Promise<ClientReadinessSnapshot> {
  return invokeTransition("client_bootstrap_ready", launchId);
}

export function clientConsoleNavigating(
  launchId: number,
): Promise<ClientReadinessSnapshot> {
  return invokeTransition("client_console_navigating", launchId);
}

export function clientConsoleReady(
  launchId: number,
): Promise<ClientReadinessSnapshot> {
  return invokeTransition("client_console_ready", launchId);
}

export async function observeBackendReady(
  onReady: (payload: ClientBackendReadyPayload) => void,
): Promise<UnlistenFn> {
  let launchId: number | null = null;
  const pending: ClientBackendReadyPayload[] = [];
  const accept = (value: unknown) => {
    let payload: ClientBackendReadyPayload;
    try {
      payload = parseBackendReadyPayload(value);
    } catch {
      return;
    }
    if (launchId === null) {
      pending.push(payload);
    } else if (payload.launchId === launchId) {
      onReady(payload);
    }
  };

  const unlisten = await listen<unknown>(BACKEND_READY_EVENT, (event) => {
    accept(event.payload);
  });
  try {
    const snapshot = await clientReadinessSnapshot();
    launchId = snapshot.launchId;
    if (
      snapshot.phase === "backendReady" &&
      snapshot.backendPort !== null &&
      snapshot.consoleUrl
    ) {
      onReady({
        schemaVersion: 1,
        launchId,
        port: snapshot.backendPort,
        consoleUrl: snapshot.consoleUrl,
      });
    }
    pending.forEach(accept);
    return unlisten;
  } catch (error) {
    unlisten();
    throw error;
  }
}

export function buildDesktopConsoleUrl(
  consoleUrl: string,
  launchId: number,
  now = Date.now(),
): string {
  const url = new URL(consoleUrl);
  url.searchParams.set("desktop", "1");
  url.searchParams.set("launchId", String(launchId));
  url.searchParams.set("_", String(now));
  return url.toString();
}

export async function reportBootstrapReadyAfterPaint(
  requestFrame: typeof requestAnimationFrame = requestAnimationFrame,
): Promise<ClientReadinessSnapshot> {
  await new Promise<void>((resolve) => {
    requestFrame(() => requestFrame(() => resolve()));
  });
  const snapshot = await clientReadinessSnapshot();
  if (snapshot.phase !== "bootstrapCreating") {
    return snapshot;
  }
  return clientBootstrapReady(snapshot.launchId);
}
