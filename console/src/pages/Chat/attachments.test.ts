import { describe, expect, it } from "vitest";
import { wrapChatResponseUsageStream } from "./turnUsage";

describe("multimodal attachment UTF-8 boundaries", () => {
  it("preserves an SSE stream when a four-byte filename is split across chunks", async () => {
    const text = 'data: {"type":"message","name":"附件😀.mp4"}\n\n';
    const bytes = new TextEncoder().encode(text);
    const emoji = new TextEncoder().encode("😀");
    let marker = -1;
    for (let index = 0; index <= bytes.length - emoji.length; index += 1) {
      if (emoji.every((value, offset) => bytes[index + offset] === value)) {
        marker = index;
        break;
      }
    }
    expect(marker).toBeGreaterThan(0);
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, marker + 2));
        controller.enqueue(bytes.slice(marker + 2));
        controller.close();
      },
    });
    const wrapped = wrapChatResponseUsageStream(
      new Response(body, {
        headers: { "Content-Type": "text/event-stream; charset=utf-8" },
      }),
      { current: null },
    );
    await expect(wrapped.text()).resolves.toBe(text);
  });
});
