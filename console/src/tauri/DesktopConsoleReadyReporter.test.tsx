import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const runtimeMocks = vi.hoisted(() => ({ isTauriRuntime: vi.fn() }));
const readinessMocks = vi.hoisted(() => ({ clientConsoleReady: vi.fn() }));

vi.mock("./backendRuntime", () => runtimeMocks);
vi.mock("./clientReadiness", () => readinessMocks);

import ConsoleLoadingShell from "../components/ConsoleLoadingShell";
import DesktopConsoleReadyReporter from "./DesktopConsoleReadyReporter";

describe("DesktopConsoleReadyReporter", () => {
  let frames: FrameRequestCallback[];

  beforeEach(() => {
    frames = [];
    runtimeMocks.isTauriRuntime.mockReset().mockReturnValue(true);
    readinessMocks.clientConsoleReady.mockReset().mockResolvedValue({});
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn((callback: FrameRequestCallback) => {
        frames.push(callback);
        return frames.length;
      }),
    );
    window.history.replaceState(null, "", "/console?desktop=1&launchId=42");
  });

  it("reports a committed route after two frames before exposing the marker", async () => {
    render(
      <DesktopConsoleReadyReporter>
        <main>工作台</main>
      </DesktopConsoleReadyReporter>,
    );

    expect(
      screen.getByText("工作台").closest("[data-go-claw-console-ready]"),
    ).toBeNull();
    expect(readinessMocks.clientConsoleReady).not.toHaveBeenCalled();

    await act(async () => frames.shift()?.(1));
    expect(readinessMocks.clientConsoleReady).not.toHaveBeenCalled();

    await act(async () => frames.shift()?.(2));

    expect(readinessMocks.clientConsoleReady).toHaveBeenCalledWith(42);
    expect(screen.getByText("工作台").parentElement).toHaveAttribute(
      "data-go-claw-console-ready",
      "1",
    );
    expect(screen.getByText("工作台").parentElement).toHaveAttribute(
      "data-go-claw-launch-id",
      "42",
    );
  });

  it("renders the browser marker without invoking Tauri", async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(false);
    window.history.replaceState(null, "", "/console");

    render(
      <DesktopConsoleReadyReporter>
        <main>登录</main>
      </DesktopConsoleReadyReporter>,
    );
    await act(async () => frames.shift()?.(1));
    await act(async () => frames.shift()?.(2));

    expect(readinessMocks.clientConsoleReady).not.toHaveBeenCalled();
    expect(screen.getByText("登录").parentElement).toHaveAttribute(
      "data-go-claw-console-ready",
      "1",
    );
  });

  it("shows branded loading content without reporting route readiness", () => {
    render(<ConsoleLoadingShell label="正在验证登录状态" />);

    expect(screen.getByAltText("GO CLAW")).toBeVisible();
    expect(screen.getByText("正在验证登录状态")).toBeVisible();
    expect(readinessMocks.clientConsoleReady).not.toHaveBeenCalled();
  });

  it("keeps the readiness marker suppressed for the CI blank hook", async () => {
    window.history.replaceState(
      null,
      "",
      "/console?desktop=1&launchId=42&goClawE2eBlank=1",
    );

    render(
      <DesktopConsoleReadyReporter>
        <main>强制未就绪</main>
      </DesktopConsoleReadyReporter>,
    );
    await act(async () => frames.shift()?.(1));
    await act(async () => frames.shift()?.(2));

    expect(readinessMocks.clientConsoleReady).not.toHaveBeenCalled();
    expect(screen.getByText("强制未就绪").parentElement).not.toHaveAttribute(
      "data-go-claw-console-ready",
    );
  });
});
