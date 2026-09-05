import { readFileSync } from "node:fs";
import {
  act,
  render,
  screen,
  waitFor,
  fireEvent,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  updatesApi,
  watchUpdateStatus,
  decodeUpdateStatus,
} from "../api/modules/updates";
import {
  DesktopUpdateProvider,
  useDesktopUpdate,
  shouldAcceptStatus,
} from "./DesktopUpdateContext";

vi.mock("../api/modules/updates", async (original) => {
  const actual = await original<typeof import("../api/modules/updates")>();
  return {
    ...actual,
    watchUpdateStatus: vi.fn(),
    updatesApi: {
      status: vi.fn(),
      check: vi.fn(),
      download: vi.fn(),
      install: vi.fn(),
      installVersion: vi.fn(),
    },
  };
});
const fixture = decodeUpdateStatus(
  JSON.parse(
    readFileSync(
      "../docs/contracts/v2.1.2/fixtures/update-status.valid.json",
      "utf8",
    ),
  ),
);

function Consumer({ id }: { id: string }) {
  const state = useDesktopUpdate();
  return (
    <div>
      <span data-testid={id}>
        {String(state.notifyAvailable)}:{state.status?.revision}
      </span>
      <button onClick={() => void state.install()}>install-{id}</button>
    </div>
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(updatesApi.status).mockResolvedValue(fixture);
  vi.mocked(updatesApi.install).mockResolvedValue(fixture);
  vi.mocked(watchUpdateStatus).mockImplementation(
    (signal) =>
      new Promise<void>((resolve) =>
        signal.addEventListener("abort", () => resolve(), { once: true }),
      ),
  );
});
describe("shared update context", () => {
  it("rejects older/equal revisions and v1 responses after accepting v2", () => {
    expect(shouldAcceptStatus(fixture, { ...fixture, revision: 3 })).toBe(
      false,
    );
    expect(shouldAcceptStatus(fixture, fixture)).toBe(false);
    expect(
      shouldAcceptStatus(fixture, { ...fixture, schemaVersion: undefined }),
    ).toBe(false);
    expect(shouldAcceptStatus(fixture, { ...fixture, revision: 5 })).toBe(true);
  });
  it("shares one stream and keeps both dots until durable installation starts", async () => {
    const view = render(
      <DesktopUpdateProvider>
        <Consumer id="gear" />
        <Consumer id="check" />
      </DesktopUpdateProvider>,
    );
    await waitFor(() => expect(watchUpdateStatus).toHaveBeenCalledTimes(1));
    expect(updatesApi.status).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("gear")).toHaveTextContent("true:4");
    fireEvent.click(screen.getByText("install-gear"));
    await waitFor(() => expect(updatesApi.install).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("gear")).toHaveTextContent("true:4");
    const push = vi.mocked(watchUpdateStatus).mock.calls[0][1];
    act(() =>
      push({
        ...fixture,
        revision: 5,
        phase: "installing",
        enginePhase: "SWITCH_PENDING",
        installationStarted: true,
        notifyAvailable: false,
      }),
    );
    expect(screen.getByTestId("gear")).toHaveTextContent("false:5");
    expect(screen.getByTestId("check")).toHaveTextContent("false:5");
    act(() => push(fixture));
    expect(screen.getByTestId("gear")).toHaveTextContent("false:5");
    view.unmount();
    expect(vi.mocked(watchUpdateStatus).mock.calls[0][0].aborted).toBe(true);
  });
});
