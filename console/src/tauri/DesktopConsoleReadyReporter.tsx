import { type ReactNode, useLayoutEffect, useState } from "react";
import { isTauriRuntime } from "./backendRuntime";
import { clientConsoleReady } from "./clientReadiness";

interface DesktopConsoleReadyReporterProps {
  children: ReactNode;
}

function readLaunchId(): number | null {
  const value = new URLSearchParams(window.location.search).get("launchId");
  if (!value || !/^\d+$/.test(value)) return null;
  const launchId = Number(value);
  return Number.isSafeInteger(launchId) && launchId > 0 ? launchId : null;
}

export default function DesktopConsoleReadyReporter({
  children,
}: DesktopConsoleReadyReporterProps) {
  const [launchId] = useState(readLaunchId);
  const [ready, setReady] = useState(false);

  useLayoutEffect(() => {
    let cancelled = false;
    if (
      new URLSearchParams(window.location.search).get("goClawE2eBlank") === "1"
    ) {
      return () => {
        cancelled = true;
      };
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (cancelled) return;
        const report =
          isTauriRuntime() && launchId !== null
            ? clientConsoleReady(launchId)
            : Promise.resolve();
        void report
          .then(() => {
            if (!cancelled) setReady(true);
          })
          .catch((error: unknown) => {
            console.error("Failed to activate the desktop console", error);
          });
      });
    });
    return () => {
      cancelled = true;
    };
  }, [launchId]);

  return (
    <div
      style={{ display: "contents" }}
      {...(ready ? { "data-go-claw-console-ready": "1" } : {})}
      {...(ready && launchId !== null
        ? { "data-go-claw-launch-id": String(launchId) }
        : {})}
    >
      {children}
    </div>
  );
}
