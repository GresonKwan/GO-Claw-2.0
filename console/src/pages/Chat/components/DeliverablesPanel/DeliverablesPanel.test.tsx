import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeliverablesEnvelope } from "@/api/modules/deliverables";
import DeliverablesPanel from ".";
import { deliverablesApi } from "@/api/modules/deliverables";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { name?: string; count?: number }) =>
      ({
        "deliverables.title": "交付产物",
        "deliverables.open": "打开",
        "deliverables.reveal": "在文件夹中显示",
        "deliverables.previewNamed": `预览 ${values?.name ?? ""}`,
        "deliverables.revealNamed": `在文件夹中显示 ${values?.name ?? ""}`,
        "deliverables.mediaRegion": "图片和视频交付产物",
        "deliverables.missing": "文件已移动或删除",
        "deliverables.loading": "正在加载预览…",
        "deliverables.collapse": "收起",
        "deliverables.showMore": `查看其余 ${values?.count ?? 0} 项`,
      })[key] ?? key,
  }),
}));

vi.mock("@/api/modules/deliverables", async (load) => {
  const actual = await load<typeof import("@/api/modules/deliverables")>();
  return {
    ...actual,
    deliverablesApi: {
      ...actual.deliverablesApi,
      open: vi.fn().mockResolvedValue({ ok: true, action: "reveal" }),
      mediaTicket: vi
        .fn()
        .mockResolvedValue({ ticket: "ticket", expiresAt: 1 }),
      mediaUrl: vi.fn(() => "/media"),
    },
  };
});

beforeAll(() => {
  class Observer {
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", Observer);
});

const envelope: DeliverablesEnvelope = {
  schemaVersion: 1,
  agentId: "default",
  chatId: "chat",
  turnId: "turn",
  responseId: "response",
  revision: 1,
  status: "ready",
  items: [
    {
      id: "image",
      turnId: "turn",
      name: "猫咪.png",
      kind: "image",
      mimeType: "image/png",
      sizeBytes: 1024,
      exists: true,
      directOpenAllowed: false,
      previewAllowed: true,
      previewKind: "image",
      createdAt: "2026-09-05T00:00:00Z",
    },
    {
      id: "danger",
      turnId: "turn",
      name: "修复.cmd",
      kind: "other",
      mimeType: "application/octet-stream",
      sizeBytes: 20,
      exists: true,
      directOpenAllowed: false,
      previewAllowed: false,
      previewKind: null,
      createdAt: "2026-09-05T00:00:00Z",
    },
  ],
};

describe("DeliverablesPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders media separately and keeps unsafe direct open disabled", async () => {
    render(<DeliverablesPanel envelope={envelope} />);
    expect(
      screen.getByRole("region", { name: "交付产物" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "预览 猫咪.png" })).toBeEnabled();
    fireEvent.click(
      screen.getByRole("button", { name: "在文件夹中显示 猫咪.png" }),
    );
    await waitFor(() =>
      expect(deliverablesApi.open).toHaveBeenCalledWith("image", "reveal"),
    );
  });

  it("opens an image in the current-page dialog and restores focus", async () => {
    render(<DeliverablesPanel envelope={envelope} />);
    const trigger = screen.getByRole("button", { name: "预览 猫咪.png" });
    fireEvent.click(trigger);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(
      await screen.findByRole("img", { name: "猫咪.png" }),
    ).toHaveAttribute("src", "/media");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("hides empty and unavailable envelopes", () => {
    const { container, rerender } = render(
      <DeliverablesPanel envelope={null} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(
      <DeliverablesPanel
        envelope={{ ...envelope, status: "unavailable", items: [] }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
