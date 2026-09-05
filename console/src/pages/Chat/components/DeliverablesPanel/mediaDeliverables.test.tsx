import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import MediaDeliverablesRail from "./MediaDeliverablesRail";
import { deliverablesApi } from "@/api/modules/deliverables";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { name?: string }) =>
      ({
        "deliverables.previewNamed": `预览 ${values?.name ?? ""}`,
        "deliverables.revealNamed": `在文件夹中显示 ${values?.name ?? ""}`,
        "deliverables.mediaRegion": "图片和视频交付产物",
      })[key] ?? key,
  }),
}));

vi.mock("@/api/modules/deliverables", () => ({
  deliverablesApi: {
    mediaTicket: vi.fn().mockRejectedValue(new Error("offline")),
    mediaUrl: vi.fn(),
  },
}));

beforeAll(() => {
  class Observer {
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", Observer);
  Element.prototype.scrollBy = vi.fn();
});

const item = {
  id: "video",
  turnId: "turn",
  name: "result.mp4",
  kind: "video" as const,
  mimeType: "video/mp4",
  sizeBytes: 500,
  exists: true,
  directOpenAllowed: false,
  previewAllowed: true,
  previewKind: "video" as const,
  createdAt: "2026-09-05T00:00:00Z",
};

describe("media deliverables rail", () => {
  it("supports keyboard navigation and uses an out-of-flow scrollbar", () => {
    const { container } = render(
      <MediaDeliverablesRail
        items={[item]}
        onPreview={vi.fn()}
        onReveal={vi.fn()}
      />,
    );
    const rail = screen.getByRole("region", { name: "图片和视频交付产物" });
    fireEvent.keyDown(rail, { key: "ArrowRight" });
    expect(Element.prototype.scrollBy).toHaveBeenCalledWith({
      left: 196,
      behavior: "smooth",
    });
    const overlay = container.querySelector(
      '[data-testid="deliverables-scroll-overlay"]',
    );
    expect(overlay).toBeInTheDocument();
    expect(getComputedStyle(overlay as Element).position).toBe("absolute");
  });

  it("exposes both touch-safe actions without relying on hover", () => {
    render(
      <MediaDeliverablesRail
        items={[item]}
        onPreview={vi.fn()}
        onReveal={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "预览 result.mp4" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "在文件夹中显示 result.mp4" }),
    ).toBeEnabled();
  });

  it("mounts only the visible media window and adjacent cards", () => {
    const items = Array.from({ length: 100 }, (_, index) => ({
      ...item,
      id: `image-${index}`,
      name: `image-${index}.png`,
      previewKind: "image" as const,
      kind: "image" as const,
      mimeType: "image/png",
    }));
    render(
      <MediaDeliverablesRail
        items={items}
        onPreview={vi.fn()}
        onReveal={vi.fn()}
      />,
    );

    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(deliverablesApi.mediaTicket).toHaveBeenCalledTimes(2);
    expect(screen.queryByLabelText("image-99.png")).not.toBeInTheDocument();
  });
});
