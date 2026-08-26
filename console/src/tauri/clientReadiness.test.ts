import { beforeEach, describe, expect, it, vi } from "vitest";

const tauriMocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauriMocks.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: tauriMocks.listen }));

import {
  BACKEND_READY_EVENT,
  buildDesktopConsoleUrl,
  clientBootstrapReady,
  clientConsoleNavigating,
  observeBackendReady,
  parseClientReadinessSnapshot,
  reportBootstrapReadyAfterPaint,
} from "./clientReadiness";

const snapshot = {
  schemaVersion: 1,
  launchId: 42,
  phase: "bootstrapReady",
  backendPort: null,
  consoleUrl: null,
  fallbackReason: null,
  fatalReason: null,
  browserOpened: false,
} as const;

describe("clientReadiness contract", () => {
  beforeEach(() => {
    tauriMocks.invoke.mockReset();
    tauriMocks.listen.mockReset();
  });

  it("uses the exact native command names and camelCase request", async () => {
    tauriMocks.invoke.mockResolvedValue(snapshot);

    await clientBootstrapReady(42);
    await clientConsoleNavigating(42);

    expect(tauriMocks.invoke).toHaveBeenNthCalledWith(
      1,
      "client_bootstrap_ready",
      { launchId: 42 },
    );
    expect(tauriMocks.invoke).toHaveBeenNthCalledWith(
      2,
      "client_console_navigating",
      { launchId: 42 },
    );
    expect(BACKEND_READY_EVENT).toBe("go-claw-client-backend-ready");
  });

  it("registers the listener before taking the readiness snapshot", async () => {
    const order: string[] = [];
    tauriMocks.listen.mockImplementation(async () => {
      order.push("listen");
      return vi.fn();
    });
    tauriMocks.invoke.mockImplementation(async () => {
      order.push("snapshot");
      return snapshot;
    });

    const stop = await observeBackendReady(vi.fn());

    expect(order).toEqual(["listen", "snapshot"]);
    stop();
  });

  it("rejects stale native events", async () => {
    let nativeHandler: ((event: { payload: unknown }) => void) | undefined;
    const onReady = vi.fn();
    tauriMocks.listen.mockImplementation(async (_name, handler) => {
      nativeHandler = handler;
      return vi.fn();
    });
    tauriMocks.invoke.mockResolvedValue(snapshot);
    await observeBackendReady(onReady);

    nativeHandler?.({
      payload: {
        schemaVersion: 1,
        launchId: 41,
        port: 54321,
        consoleUrl: "http://127.0.0.1:54321/console",
      },
    });

    expect(onReady).not.toHaveBeenCalled();
  });

  it("rejects missing and extra snapshot fields", () => {
    expect(() =>
      parseClientReadinessSnapshot({ ...snapshot, browserOpened: undefined }),
    ).toThrow("invalid client readiness snapshot");
    expect(() =>
      parseClientReadinessSnapshot({ ...snapshot, extra: true }),
    ).toThrow("invalid client readiness snapshot");
  });

  it("builds the exact versioned console URL", () => {
    expect(
      buildDesktopConsoleUrl(
        "http://127.0.0.1:54321/console",
        42,
        1_777_777_777_000,
      ),
    ).toBe(
      "http://127.0.0.1:54321/console?desktop=1&launchId=42&_=1777777777000",
    );
  });

  it("reports bootstrap readiness only after two animation frames", async () => {
    const frames: FrameRequestCallback[] = [];
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      frames.push(callback);
      return frames.length;
    });
    tauriMocks.invoke
      .mockResolvedValueOnce({ ...snapshot, phase: "bootstrapCreating" })
      .mockResolvedValueOnce(snapshot);

    const report = reportBootstrapReadyAfterPaint(requestFrame);
    expect(tauriMocks.invoke).not.toHaveBeenCalled();

    frames.shift()?.(1);
    expect(tauriMocks.invoke).not.toHaveBeenCalled();

    frames.shift()?.(2);
    await report;

    expect(requestFrame).toHaveBeenCalledTimes(2);
    expect(tauriMocks.invoke).toHaveBeenNthCalledWith(
      1,
      "client_readiness_snapshot",
    );
    expect(tauriMocks.invoke).toHaveBeenNthCalledWith(
      2,
      "client_bootstrap_ready",
      { launchId: 42 },
    );
  });
});
