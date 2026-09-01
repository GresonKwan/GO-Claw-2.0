import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckOutlined,
  DownOutlined,
  LoadingOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Dropdown } from "antd";
import { goClawProductApi } from "@/api/modules/goClawProduct";
import type {
  ModelTierId,
  ModelTierResponse,
  PublicModelTier,
} from "@/api/types/goClawProduct";
import { MODEL_TIER_ICONS } from "@/components/modelTierIcons";
import { useAppMessage } from "@/hooks/useAppMessage";
import { useAgentStore } from "@/stores/agentStore";
import { useTurnUsageStore } from "../turnUsageStore";
import styles from "./index.module.less";

function publishActiveMaxInputLength(value: number): void {
  useTurnUsageStore.getState().setActiveMaxInputLength(value);
  if (value > 0) {
    window.dispatchEvent(
      new CustomEvent("model-switched", {
        detail: { maxInputLength: value },
      }),
    );
  }
}

function TierIcon({ tier }: { tier: PublicModelTier }) {
  return (
    <img
      className={styles.tierIcon}
      src={MODEL_TIER_ICONS[tier.icon]}
      alt={tier.label}
    />
  );
}

export default function ModelSelector() {
  const { selectedAgent } = useAgentStore();
  const { message } = useAppMessage();
  const [data, setData] = useState<ModelTierResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    try {
      const next = await goClawProductApi.getModelTier(selectedAgent);
      if (sequence !== requestSequence.current) return;
      setData(next);
      publishActiveMaxInputLength(next.effectiveMaxInputLength);
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      console.error("Failed to load employee model tier", error);
      setData(null);
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [selectedAgent]);

  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
    };
  }, [load]);

  const selectTier = async (tier: ModelTierId) => {
    if (!data || saving || tier === data.selectedTier) {
      setOpen(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await goClawProductApi.setModelTier({
        schemaVersion: 1,
        agentId: selectedAgent,
        tier,
      });
      setData(updated);
      publishActiveMaxInputLength(updated.effectiveMaxInputLength);
      setOpen(false);
    } catch (error) {
      console.error("Failed to save employee model tier", error);
      message.error("模型档位保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  const selected = data?.tiers.find((tier) => tier.id === data.selectedTier);
  if (loading) {
    return (
      <button
        type="button"
        className={styles.trigger}
        disabled
        aria-label="加载模型档位"
      >
        <LoadingOutlined />
        <span>加载中</span>
        <DownOutlined className={styles.chevron} />
      </button>
    );
  }
  if (!selected) {
    return (
      <button
        type="button"
        className={styles.trigger}
        aria-label="模型档位加载失败，点击重试"
        onClick={() => void load()}
      >
        <ReloadOutlined />
        <span>重新加载</span>
        <DownOutlined className={styles.chevron} />
      </button>
    );
  }
  const panel = (
    <div className={styles.panel} role="menu" aria-label="模型档位">
      <div className={styles.panelTitle}>选择模型档位</div>
      {data?.tiers.map((tier) => {
        const active = tier.id === data.selectedTier;
        return (
          <button
            key={tier.id}
            type="button"
            role="menuitem"
            className={`${styles.tierOption} ${active ? styles.active : ""}`}
            disabled={saving}
            onClick={() => void selectTier(tier.id)}
          >
            <TierIcon tier={tier} />
            <span className={styles.tierCopy}>
              <span className={styles.tierName}>{tier.label}</span>
              <span className={styles.tierDescription}>{tier.description}</span>
              {tier.warning && (
                <span className={styles.tierWarning}>{tier.warning}</span>
              )}
            </span>
            {active && <CheckOutlined className={styles.check} />}
          </button>
        );
      })}
    </div>
  );

  return (
    <Dropdown
      open={open}
      onOpenChange={(next) => !saving && setOpen(next)}
      trigger={["click"]}
      popupRender={() => panel}
      placement="bottomLeft"
    >
      <button
        type="button"
        className={styles.trigger}
        aria-label={selected.label}
      >
        <TierIcon tier={selected} />
        <span>{selected.label}</span>
        <DownOutlined className={styles.chevron} />
      </button>
    </Dropdown>
  );
}
