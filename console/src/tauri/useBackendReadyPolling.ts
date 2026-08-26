import { useCallback, useEffect, useRef, useState } from "react";
import {
  getBackendStartupError,
  restartBackend,
  shouldUseTauriStartupGate,
} from "./backendRuntime";
import {
  observeBackendReady,
  type ClientBackendReadyPayload,
} from "./clientReadiness";

export type BackendReadyStatus = "checking" | "ready" | "timeout" | "error";

export const BACKEND_POLL_INTERVAL_MS = 1000;
export const BACKEND_POLL_TIMEOUT_SECONDS = 180;
export const BACKEND_REQUEST_TIMEOUT_MS = 2500;
export const BACKEND_STARTUP_ERROR_POLL_INTERVAL_MS = 3000;

interface BackendReadyPollingState {
  shouldGate: boolean;
  status: BackendReadyStatus;
  elapsed: number;
  totalSec: number;
  errorMessage: string;
  readyUrl: string;
  launchId: number | null;
  retry: () => void;
}

export default function useBackendReadyPolling(): BackendReadyPollingState {
  const shouldGate = shouldUseTauriStartupGate();
  const [status, setStatus] = useState<BackendReadyStatus>("checking");
  const [elapsed, setElapsed] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [readyUrl, setReadyUrl] = useState("");
  const [launchId, setLaunchId] = useState<number | null>(null);
  const runRef = useRef(0);
  const cancelPollingRef = useRef<(() => void) | null>(null);

  const cancelPolling = useCallback(() => {
    runRef.current += 1;
    cancelPollingRef.current?.();
    cancelPollingRef.current = null;
  }, []);

  const showStartupFailure = useCallback(
    async (runId: number, fallbackStatus: BackendReadyStatus = "timeout") => {
      const startupError = await getBackendStartupError().catch(() => "");
      if (runRef.current !== runId) return;
      if (startupError) {
        setErrorMessage(startupError);
        setStatus("error");
      } else {
        setStatus(fallbackStatus);
      }
    },
    [],
  );

  const startPolling = useCallback(() => {
    cancelPolling();
    const runId = runRef.current;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let unlisten: (() => void) | null = null;
    let candidate: ClientBackendReadyPayload | null = null;
    let polling = false;
    let cancelled = false;

    cancelPollingRef.current = () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
      unlisten?.();
      timer = null;
      controller = null;
      unlisten = null;
    };

    setStatus("checking");
    setElapsed(0);
    setErrorMessage("");
    setReadyUrl("");
    setLaunchId(null);

    const start = Date.now();
    let lastStartupErrorCheckAt = 0;

    const schedule = (delay: number) => {
      if (cancelled || runRef.current !== runId) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => void poll(), delay);
    };

    const checkStartupError = async (): Promise<boolean> => {
      const startupError = await getBackendStartupError().catch(() => "");
      if (runRef.current !== runId) return true;
      if (!startupError) return false;

      setErrorMessage(startupError);
      setStatus("error");
      return true;
    };

    const poll = async () => {
      if (polling || cancelled || runRef.current !== runId) return;
      polling = true;
      try {
        if (candidate) {
          try {
            controller = new AbortController();
            const timeoutId = setTimeout(
              () => controller?.abort(),
              BACKEND_REQUEST_TIMEOUT_MS,
            );
            try {
              const versionUrl = new URL("/api/version", candidate.consoleUrl);
              const res = await fetch(versionUrl, {
                signal: controller.signal,
                cache: "no-store",
              });
              if (runRef.current === runId && res.ok) {
                setReadyUrl(candidate.consoleUrl);
                setLaunchId(candidate.launchId);
                setStatus("ready");
                return;
              }
            } finally {
              clearTimeout(timeoutId);
              controller = null;
            }
          } catch {
            // Native readiness identifies the candidate; HTTP proves it is usable.
          }
        }

        if (runRef.current !== runId) return;
        const now = Date.now();
        const seconds = Math.round((now - start) / 1000);
        if (
          lastStartupErrorCheckAt === 0 ||
          now - lastStartupErrorCheckAt >=
            BACKEND_STARTUP_ERROR_POLL_INTERVAL_MS
        ) {
          lastStartupErrorCheckAt = now;
          if (await checkStartupError()) return;
        }
        if (runRef.current !== runId) return;
        setElapsed(seconds);
        if (seconds >= BACKEND_POLL_TIMEOUT_SECONDS) {
          if (!(await checkStartupError()) && runRef.current === runId) {
            setStatus("timeout");
          }
          return;
        }
        schedule(BACKEND_POLL_INTERVAL_MS);
      } finally {
        polling = false;
      }
    };

    void observeBackendReady((payload) => {
      if (cancelled || runRef.current !== runId) return;
      candidate = payload;
      schedule(0);
    })
      .then((stop) => {
        if (cancelled || runRef.current !== runId) {
          stop();
        } else {
          unlisten = stop;
        }
      })
      .catch(() => {
        // Startup-error polling below still provides a clear terminal state.
      });

    void poll();
  }, [cancelPolling]);

  const retry = useCallback(() => {
    cancelPolling();
    const runId = runRef.current;
    setStatus("checking");
    setElapsed(0);
    setErrorMessage("");
    setReadyUrl("");
    setLaunchId(null);

    restartBackend()
      .then(() => {
        if (runRef.current !== runId) return;
        startPolling();
      })
      .catch(() => {
        void showStartupFailure(runId);
      });
  }, [cancelPolling, showStartupFailure, startPolling]);

  useEffect(() => {
    if (!shouldGate) return undefined;

    startPolling();

    return cancelPolling;
  }, [cancelPolling, shouldGate, showStartupFailure, startPolling]);

  return {
    shouldGate,
    status,
    elapsed,
    totalSec: BACKEND_POLL_TIMEOUT_SECONDS,
    errorMessage,
    readyUrl,
    launchId,
    retry,
  };
}
