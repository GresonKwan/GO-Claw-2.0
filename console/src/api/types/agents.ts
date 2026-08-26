// Multi-agent management types

import type { ModelTierId } from "./goClawProduct";

export type AgentStartupStatus =
  | "disabled"
  | "pending"
  | "starting"
  | "running"
  | "failed";

export interface AgentSummary {
  id: string;
  name: string;
  description: string;
  workspace_dir: string;
  enabled: boolean;
  pinned?: boolean;
  startup_status?: AgentStartupStatus;
  model_tier?: ModelTierId;
}

export interface AgentListResponse {
  agents: AgentSummary[];
}

export interface ReorderAgentsResponse {
  success: boolean;
  agent_ids: string[];
}

export interface AgentProfileConfig {
  id: string;
  name: string;
  description?: string;
  workspace_dir?: string;
  approval_level?: string;
  model_tier?: ModelTierId;
}

export interface CreateAgentRequest {
  id?: string;
  name: string;
  description?: string;
  workspace_dir?: string;
  language?: string;
  skill_names?: string[];
}

export interface CopyAgentRequest {
  name?: string;
  copy_agent_json?: true;
  copy_md_files?: boolean;
  copy_skills?: boolean;
  copy_jobs?: boolean;
}

export interface AgentProfileRef {
  id: string;
  workspace_dir: string;
  enabled?: boolean;
  pinned?: boolean;
}
