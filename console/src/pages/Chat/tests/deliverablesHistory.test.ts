import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatHistory, Message } from "../../../api";
import api from "../../../api";

vi.mock("../../../api/modules/deliverables", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/deliverables")
  >();
  return {
    ...actual,
    deliverablesApi: {
      ...actual.deliverablesApi,
      query: vi.fn(),
    },
  };
});

import { deliverablesApi } from "../../../api/modules/deliverables";
import sessionApi from "../sessionApi";
import { embeddedDeliverables } from "../deliverables";

const CHAT_ID = "33333333-3333-4333-8333-333333333333";
const RESPONSE_ID = "response_assistant-1";
const envelope = {
  schemaVersion: 1 as const,
  agentId: "default",
  chatId: CHAT_ID,
  turnId: "turn-1",
  responseId: RESPONSE_ID,
  revision: 1,
  status: "ready" as const,
  items: [
    {
      id: "image-1",
      turnId: "turn-1",
      name: "猫咪 图片.png",
      kind: "image" as const,
      mimeType: "image/png",
      sizeBytes: 12,
      exists: true,
      directOpenAllowed: false,
      previewAllowed: true,
      previewKind: "image" as const,
      createdAt: "2026-09-09T00:00:00Z",
    },
  ],
};

function responseEnvelope(
  session: Awaited<ReturnType<typeof sessionApi.getSession>>,
) {
  const card = session.messages?.[0]?.cards?.find(
    (candidate) => candidate.code === "AgentScopeRuntimeResponseCard",
  );
  return card?.data
    ? embeddedDeliverables(card.data as Record<string, unknown>)
    : null;
}

describe("historical deliverables hydration", () => {
  beforeEach(() => {
    const internal = sessionApi as unknown as {
      sessionList: unknown[];
      convertedSessionCache: Map<string, unknown>;
      sessionResultCache: Map<string, unknown>;
      sessionRequests: Map<string, unknown>;
    };
    internal.sessionList = [
      {
        id: CHAT_ID,
        sessionId: CHAT_ID,
        userId: "default",
        channel: "console",
        name: "history",
      },
    ];
    internal.convertedSessionCache.clear();
    internal.sessionResultCache.clear();
    internal.sessionRequests.clear();
    vi.mocked(deliverablesApi.query).mockReset();
  });

  afterEach(() => vi.restoreAllMocks());

  it("retries only deliverables hydration when an idle session LRU entry was incomplete", async () => {
    const messages: Message[] = [
      {
        id: "assistant-1",
        role: "assistant",
        content: [{ type: "text", text: "done" }],
        metadata: {},
      } as Message,
    ];
    const getChat = vi
      .spyOn(api, "getChat")
      .mockResolvedValue({ messages, status: "idle" } as ChatHistory);
    vi.mocked(deliverablesApi.query)
      .mockRejectedValueOnce(new Error("temporary index failure"))
      .mockResolvedValueOnce({ schemaVersion: 1, turns: [envelope] });

    const first = await sessionApi.getSession(CHAT_ID);
    expect(responseEnvelope(first)).toBeNull();

    const restored = await sessionApi.getSession(CHAT_ID);
    expect(responseEnvelope(restored)).toEqual(envelope);
    expect(getChat).toHaveBeenCalledTimes(1);
    expect(deliverablesApi.query).toHaveBeenCalledTimes(2);
  });
});
