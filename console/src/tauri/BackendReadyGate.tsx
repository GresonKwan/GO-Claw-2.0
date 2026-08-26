import { type ReactNode, useEffect, useRef, useState } from "react";
import BackendLoadingPage from "./BackendLoadingPage";
import useBackendReadyPolling from "./useBackendReadyPolling";
import {
  buildDesktopConsoleUrl,
  clientConsoleNavigating,
} from "./clientReadiness";

interface Props {
  children: ReactNode;
}

export async function navigateToReadyConsole(
  readyUrl: string,
  launchId: number,
  replace: (url: string) => void,
  now = Date.now(),
): Promise<void> {
  await clientConsoleNavigating(launchId);
  replace(buildDesktopConsoleUrl(readyUrl, launchId, now));
}

export default function BackendReadyGate({ children }: Props) {
  const {
    shouldGate,
    status,
    elapsed,
    totalSec,
    errorMessage,
    readyUrl,
    launchId,
    retry,
  } = useBackendReadyPolling();
  const [navigationError, setNavigationError] = useState("");
  const navigationKeyRef = useRef("");

  useEffect(() => {
    if (status === "checking") {
      setNavigationError("");
    }
  }, [status]);

  useEffect(() => {
    if (!shouldGate || status !== "ready" || !readyUrl || launchId === null) {
      return;
    }
    const navigationKey = `${launchId}:${readyUrl}`;
    if (navigationKeyRef.current === navigationKey) return;
    navigationKeyRef.current = navigationKey;
    void navigateToReadyConsole(readyUrl, launchId, (url) =>
      window.location.replace(url),
    ).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      setNavigationError(message || "Unable to activate the desktop console");
    });
  }, [launchId, readyUrl, shouldGate, status]);

  // Browser mode, or Tauri after it has navigated to the backend-hosted console.
  if (!shouldGate) {
    return <>{children}</>;
  }

  return (
    <BackendLoadingPage
      status={navigationError ? "error" : status}
      elapsed={elapsed}
      totalSec={totalSec}
      errorMessage={navigationError || errorMessage}
      onRetry={retry}
    />
  );
}
