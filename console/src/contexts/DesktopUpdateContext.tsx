import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  updatesApi,
  watchUpdateStatus,
  type UpdateStatus,
} from "../api/modules/updates";

interface ContextValue {
  status: UpdateStatus | null;
  notifyAvailable: boolean;
  actionPending: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  check: () => Promise<void>;
  download: (target?: UpdateStatus) => Promise<void>;
  install: (target?: UpdateStatus) => Promise<void>;
  installVersion: (
    version: string,
    url: string,
    signature: string,
  ) => Promise<void>;
}
const UpdateContext = createContext<ContextValue | null>(null);
export function updateErrorCode(error: unknown) {
  const message = error instanceof Error ? error.message : "";
  return (
    message.match(/^([A-Z][A-Z0-9_]{1,127})(?:$|\s|-)/)?.[1] ??
    "UPDATE_REQUEST_FAILED"
  );
}
export function shouldAcceptStatus(
  current: UpdateStatus | null,
  incoming: UpdateStatus,
) {
  if (current?.schemaVersion !== 2) return true;
  return incoming.schemaVersion === 2 && incoming.revision! > current.revision!;
}

/** Shared by browser and WebView. No Tauri update IPC or per-widget polling. */
export function DesktopUpdateProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setPending] = useState(false);
  const current = useRef<UpdateStatus | null>(null);
  const refreshTask = useRef<Promise<void> | null>(null);
  const actionTask = useRef<Promise<void> | null>(null);
  const lastRefresh = useRef(0);

  const accept = useCallback((next: UpdateStatus | null) => {
    if (!next) {
      current.current = null;
      setStatus(null);
      return;
    }
    if (shouldAcceptStatus(current.current, next)) {
      current.current = next;
      setStatus(next);
    }
  }, []);

  const refresh = useCallback(() => {
    if (refreshTask.current) return refreshTask.current;
    const task = (async () => {
      try {
        accept(await updatesApi.status());
      } catch (failure) {
        setError(updateErrorCode(failure));
      } finally {
        lastRefresh.current = Date.now();
      }
    })().finally(() => {
      refreshTask.current = null;
    });
    refreshTask.current = task;
    return task;
  }, [accept]);

  useEffect(() => {
    let disposed = false;
    let stream: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let wake: (() => void) | undefined;
    const pause = (ms: number) =>
      new Promise<void>((resolve) => {
        wake = resolve;
        timer = setTimeout(resolve, ms);
      });
    const onFocus = () => {
      if (!document.hidden && Date.now() - lastRefresh.current >= 1000)
        void refresh();
    };
    const onVisibility = () => {
      stream?.abort();
      clearTimeout(timer);
      wake?.();
      onFocus();
    };
    void (async () => {
      while (!disposed) {
        await refresh();
        if (disposed) return;
        if (!document.hidden && current.current?.schemaVersion === 2) {
          stream = new AbortController();
          try {
            await watchUpdateStatus(
              stream.signal,
              accept,
              current.current.revision,
            );
          } catch {
            // Stream failure falls back to one shared ten-second poll.
          }
        }
        if (!disposed) await pause(document.hidden ? 60_000 : 10_000);
      }
    })();
    window.addEventListener("focus", onFocus);
    window.addEventListener("online", onVisibility);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      stream?.abort();
      clearTimeout(timer);
      wake?.();
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("online", onVisibility);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [accept, refresh]);

  const action = useCallback(
    (operation: () => Promise<UpdateStatus | null>) => {
      if (actionTask.current) return actionTask.current;
      setPending(true);
      setError(null);
      const task = (async () => {
        try {
          accept(await operation());
        } catch (failure) {
          setError(updateErrorCode(failure));
          await refresh();
        } finally {
          setPending(false);
        }
      })().finally(() => {
        actionTask.current = null;
      });
      actionTask.current = task;
      return task;
    },
    [accept, refresh],
  );

  const notifyAvailable =
    status?.schemaVersion === 2
      ? status.notifyAvailable === true
      : Boolean(
          status?.latest?.isNewer &&
            status.phase !== "installing" &&
            status.phase !== "idle",
        );
  return (
    <UpdateContext.Provider
      value={{
        status,
        notifyAvailable,
        actionPending,
        error,
        refresh,
        check: () => action(updatesApi.check),
        download: (target) =>
          action(() =>
            updatesApi.download(target ?? current.current ?? undefined),
          ),
        install: (target) =>
          action(() =>
            updatesApi.install(target ?? current.current ?? undefined),
          ),
        installVersion: (version, url, signature) =>
          action(() => updatesApi.installVersion(version, url, signature)),
      }}
    >
      {children}
    </UpdateContext.Provider>
  );
}

export function useDesktopUpdate() {
  const context = useContext(UpdateContext);
  if (!context)
    throw new Error("useDesktopUpdate requires DesktopUpdateProvider");
  return context;
}
