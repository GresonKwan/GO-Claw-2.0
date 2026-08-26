export type ModelTierId = "economy" | "balanced" | "performance";
export type ModelTierIcon = "leaf" | "balance" | "rocket";

export interface PublicModelTier {
  id: ModelTierId;
  label: string;
  description: string;
  warning: string | null;
  icon: ModelTierIcon;
}

export interface ModelTierResponse {
  schemaVersion: 1;
  agentId: string;
  selectedTier: ModelTierId;
  tiers: PublicModelTier[];
  effectiveMaxInputLength: number;
}

export interface SetModelTierRequest {
  schemaVersion: 1;
  agentId: string;
  tier: ModelTierId;
}
