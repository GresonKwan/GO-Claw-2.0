import economyIcon from "@/assets/model-tiers/economy.svg";
import balancedIcon from "@/assets/model-tiers/balanced.svg";
import performanceIcon from "@/assets/model-tiers/performance.svg";
import type { ModelTierIcon, PublicModelTier } from "@/api/types/goClawProduct";

export const MODEL_TIER_ICONS: Record<ModelTierIcon, string> = {
  leaf: economyIcon,
  balance: balancedIcon,
  rocket: performanceIcon,
};

export const MODEL_TIER_PRESENTATION: PublicModelTier[] = [
  {
    id: "economy",
    label: "经济",
    description: "适合日常任务，额度更耐用",
    warning: null,
    icon: "leaf",
  },
  {
    id: "balanced",
    label: "均衡",
    description: "质量与额度消耗更均衡",
    warning: null,
    icon: "balance",
  },
  {
    id: "performance",
    label: "高性能",
    description: "适合复杂和高要求任务",
    warning: "高性能模型可以提高任务完成质量，但额度消耗更快。",
    icon: "rocket",
  },
];

export function getModelTierPresentation(id: string | undefined) {
  return (
    MODEL_TIER_PRESENTATION.find((tier) => tier.id === id) ??
    MODEL_TIER_PRESENTATION[0]
  );
}
