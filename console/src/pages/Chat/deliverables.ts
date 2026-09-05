import type { DeliverablesEnvelope } from "@/api/modules/deliverables";

export function responseId(data: Record<string, unknown>): string | null {
  return typeof data.id === "string" && data.id ? data.id : null;
}

export function embeddedDeliverables(
  data: Record<string, unknown>,
): DeliverablesEnvelope | null {
  const metadata =
    data.metadata && typeof data.metadata === "object"
      ? (data.metadata as Record<string, unknown>)
      : null;
  const value =
    (data.goClawDeliverables as unknown) ?? metadata?.goClawDeliverables;
  if (!value || typeof value !== "object") return null;
  const envelope = value as DeliverablesEnvelope;
  return envelope.schemaVersion === 1 && Array.isArray(envelope.items)
    ? envelope
    : null;
}

export function attachDeliverables(
  messages: Array<{
    cards?: Array<{ code?: string; data?: Record<string, unknown> }>;
  }>,
  turns: DeliverablesEnvelope[],
): void {
  const byResponse = new Map(turns.map((turn) => [turn.responseId, turn]));
  for (const message of messages) {
    const card = message.cards?.find(
      (candidate) => candidate.code === "AgentScopeRuntimeResponseCard",
    );
    const id = card?.data ? responseId(card.data) : null;
    if (id && card?.data && byResponse.has(id)) {
      card.data.goClawDeliverables = byResponse.get(id);
    }
  }
}
