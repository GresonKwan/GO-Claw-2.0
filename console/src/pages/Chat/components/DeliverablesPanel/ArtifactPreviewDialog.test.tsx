import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ArtifactPreviewDialog from "./ArtifactPreviewDialog";
import { deliverablesApi } from "@/api/modules/deliverables";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@/api/modules/deliverables", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("@/api/modules/deliverables")
  >();
  return {
    ...actual,
    deliverablesApi: {
      ...actual.deliverablesApi,
      mediaTicket: vi.fn(),
      mediaUrl: vi.fn(),
    },
  };
});

const item = {
  id: "image-1",
  turnId: "turn-1",
  name: "猫咪 图片.png",
  kind: "image" as const,
  mimeType: "image/png",
  sizeBytes: 20,
  exists: true,
  directOpenAllowed: false,
  previewAllowed: true,
  previewKind: "image" as const,
  createdAt: "2026-09-09T00:00:00Z",
};

describe("ArtifactPreviewDialog", () => {
  beforeEach(() => {
    vi.mocked(deliverablesApi.mediaTicket).mockReset();
    vi.mocked(deliverablesApi.mediaUrl).mockReset();
  });

  it("renews an expired image ticket once and then shows an explicit failure", async () => {
    vi.mocked(deliverablesApi.mediaTicket)
      .mockResolvedValueOnce({ ticket: "expired", expiresAt: 1 })
      .mockResolvedValueOnce({ ticket: "fresh", expiresAt: 2 });
    vi.mocked(deliverablesApi.mediaUrl)
      .mockReturnValueOnce("/expired-image")
      .mockReturnValueOnce("/fresh-image");

    render(<ArtifactPreviewDialog item={item} open onClose={vi.fn()} />);
    const first = await screen.findByRole("img", { name: item.name });
    expect(first).toHaveAttribute("src", "/expired-image");
    fireEvent.error(first);

    const renewed = await screen.findByRole("img", { name: item.name });
    await waitFor(() => expect(renewed).toHaveAttribute("src", "/fresh-image"));
    expect(deliverablesApi.mediaTicket).toHaveBeenCalledTimes(2);

    fireEvent.error(renewed);
    expect(
      await screen.findByText("deliverables.previewFailed"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: item.name }),
    ).not.toBeInTheDocument();
  });

  it("retries one transient ticket request failure", async () => {
    vi.mocked(deliverablesApi.mediaTicket)
      .mockRejectedValueOnce(new Error("temporary network failure"))
      .mockResolvedValueOnce({ ticket: "fresh", expiresAt: 2 });
    vi.mocked(deliverablesApi.mediaUrl).mockReturnValue("/fresh-image");

    render(<ArtifactPreviewDialog item={item} open onClose={vi.fn()} />);

    const image = await screen.findByRole("img", { name: item.name });
    expect(image).toHaveAttribute("src", "/fresh-image");
    expect(deliverablesApi.mediaTicket).toHaveBeenCalledTimes(2);
  });
});
