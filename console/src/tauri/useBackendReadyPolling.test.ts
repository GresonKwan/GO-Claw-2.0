import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const runtimeMocks = vi.hoisted(() => ({
  getBackendStartupError: vi.fn(),
  restartBackend: vi.fn(),
  shouldUseTauriStartupGate: vi.fn(() => true),
}));

const readinessMocks = vi.hoisted(() => ({
  observeBackendReady: vi.fn(),
}));

vi.mock("./backendRuntime", () => runtimeMocks);
vi.mock("./clientReadiness", () => readinessMocks);

import useBackendReadyPolling, {
  BACKEND_POLL_INTERVAL_MS,
} from "./useBackendReadyPolling";

describe("useBackendReadyPolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    runtimeMocks.getBackendStartupError.mockReset().mockResolvedValue("");
    runtimeMocks.restartBackend.mockReset().mockResolvedValue(undefined);
    runtimeMocks.shouldUseTauriStartupGate.mockReturnValue(true);
    readinessMocks.observeBackendReady.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("retries HTTP verification after a native backend-ready event", async () => {
    let onReady:
      | ((payload: {
          schemaVersion: 1;
          launchId: number;
          port: number;
          consoleUrl: string;
        }) => void)
      | undefined;
    readinessMocks.observeBackendReady.mockImplementation(async (callback) => {
      onReady = callback;
      return vi.fn();
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useBackendReadyPolling());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      onReady?.({
        schemaVersion: 1,
        launchId: 42,
        port: 54321,
        consoleUrl: "http://127.0.0.1:54321/console",
      });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("checking");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(BACKEND_POLL_INTERVAL_MS);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current).toMatchObject({
      status: "ready",
      launchId: 42,
      readyUrl: "http://127.0.0.1:54321/console",
    });
  });
});
