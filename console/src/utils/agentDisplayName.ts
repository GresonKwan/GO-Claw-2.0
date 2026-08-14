import type { TFunction } from "i18next";
import type { AgentSummary } from "../api/types/agents";

export const DEFAULT_AGENT_ID = "default";
// Upstream configurations use this exact name as the default-name sentinel.
export const DEFAULT_AGENT_DISPLAY_NAME = "Default Agent";

/** Customer label for an agent; the upstream default sentinel resolves through i18n. */
export function getAgentDisplayName(
  agent: Pick<AgentSummary, "id" | "name">,
  t: TFunction,
): string {
  // For the default employee, preserve i18n unless explicitly customized.
  if (agent.id === DEFAULT_AGENT_ID) {
    // If the name is customized (not the upstream sentinel), show it as-is.
    if (agent.name && agent.name !== DEFAULT_AGENT_DISPLAY_NAME) {
      return agent.name;
    }
    // Otherwise, use the localized customer-facing default name.
    return t("agent.defaultDisplayName");
  }
  // For other employees, use the user-defined name or fall back to the id.
  return agent.name || agent.id;
}
