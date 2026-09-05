import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
  getApiToken: () => "token-value",
}));
vi.mock("../authHeaders", () => ({
  buildAuthHeaders: () => ({ Authorization: "Bearer test" }),
}));

import { chatApi } from "./chat";

afterEach(() => vi.unstubAllGlobals());

describe("chat attachment transport", () => {
  it("keeps actual binary bytes in multipart FormData", async () => {
    const bytes = Uint8Array.from([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0xff, 0x00,
    ]);
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const part = (init.body as FormData).get("file") as File;
      expect(part.name).toBe("附件 猫咪#100%+.png");
      expect(new Uint8Array(await part.arrayBuffer())).toEqual(bytes);
      return new Response(
        JSON.stringify({
          url: "C:\\媒体\\附件 猫咪#100%+.png",
          file_name: part.name,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const file = new File([bytes], "附件 猫咪#100%+.png", {
      type: "image/png",
    });
    await expect(chatApi.uploadFile(file)).resolves.toMatchObject({
      file_name: file.name,
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("keeps a non-JSON server error distinct from an encoding error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("payload too large", { status: 413 })),
    );
    await expect(chatApi.uploadFile(new File(["x"], "a.png"))).rejects.toThrow(
      /Upload failed: 413.*payload too large/,
    );
  });

  it("encodes every preview segment exactly once", () => {
    const url = chatApi.filePreviewUrl("C:\\媒体 空格\\100%2F+#猫😀.png");
    expect(url).toBe(
      "/api/files/preview/C%3A/%E5%AA%92%E4%BD%93%20%E7%A9%BA%E6%A0%BC/100%25252F%2B%23%E7%8C%AB%F0%9F%98%80.png?token=token-value",
    );
  });
});
