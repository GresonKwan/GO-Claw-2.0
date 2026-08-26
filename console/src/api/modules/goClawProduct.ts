import { request } from "../request";
import type {
  ModelTierResponse,
  SetModelTierRequest,
} from "../types/goClawProduct";

export const goClawProductApi = {
  getModelTier: (agentId: string) =>
    request<ModelTierResponse>(
      `/go-claw/model-tier?agent_id=${encodeURIComponent(agentId)}`,
    ),

  setModelTier: (body: SetModelTierRequest) =>
    request<ModelTierResponse>("/go-claw/model-tier", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
