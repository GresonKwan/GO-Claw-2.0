import { describe, expect, it, vi } from "vitest";

const readinessMocks = vi.hoisted(() => ({
  clientConsoleNavigating: vi.fn(),
}));

vi.mock("./clientReadiness", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./clientReadiness")>();
  return {
    ...actual,
    clientConsoleNavigating: readinessMocks.clientConsoleNavigating,
  };
});

import { navigateToReadyConsole } from "./BackendReadyGate";

describe("navigateToReadyConsole", () => {
  it("waits for native navigation acknowledgement before replacing location", async () => {
    let acknowledge: (() => void) | undefined;
    readinessMocks.clientConsoleNavigating.mockReturnValue(
      new Promise<void>((resolve) => {
        acknowledge = resolve;
      }),
    );
    const replace = vi.fn();

    const navigation = navigateToReadyConsole(
      "http://127.0.0.1:54321/console",
      42,
      replace,
      1_777_777_777_000,
    );
    expect(replace).not.toHaveBeenCalled();

    acknowledge?.();
    await navigation;

    expect(readinessMocks.clientConsoleNavigating).toHaveBeenCalledWith(42);
    expect(replace).toHaveBeenCalledWith(
      "http://127.0.0.1:54321/console?desktop=1&launchId=42&_=1777777777000",
    );
  });

  it("does not navigate when native acknowledgement fails", async () => {
    readinessMocks.clientConsoleNavigating.mockRejectedValue(
      new Error("INVALID_PHASE"),
    );
    const replace = vi.fn();

    await expect(
      navigateToReadyConsole(
        "http://127.0.0.1:54321/console",
        42,
        replace,
        1_777_777_777_000,
      ),
    ).rejects.toThrow("INVALID_PHASE");
    expect(replace).not.toHaveBeenCalled();
  });
});
