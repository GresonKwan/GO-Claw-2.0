import { describe, expect, it } from "vitest";
import { attachDeliverables, embeddedDeliverables } from "./deliverables";

const envelope = {
  schemaVersion: 1 as const,
  agentId: "default",
  chatId: "chat",
  turnId: "turn",
  responseId: "response_message",
  revision: 1,
  status: "ready" as const,
  items: [],
};

describe("deliverable response binding", () => {
  it("reads live metadata and attaches historical envelopes by stable response id", () => {
    expect(
      embeddedDeliverables({ metadata: { goClawDeliverables: envelope } }),
    ).toEqual(envelope);
    const messages = [
      {
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: { id: "response_message" } as Record<string, unknown>,
          },
        ],
      },
    ];
    attachDeliverables(messages, [envelope]);
    expect(messages[0].cards[0].data.goClawDeliverables).toEqual(envelope);
  });
});
