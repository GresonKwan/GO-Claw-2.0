import { useCallback, useEffect, useState } from "react";
import { Progress, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { getQuota, type QuotaInfo } from "../api/modules/quota";
import styles from "./index.module.less";

const POLL_INTERVAL_MS = 60_000;
const LOW_QUOTA_THRESHOLD = 20;

/**
 * GO CLAW customer build: quota usage bar at the bottom of the sidebar.
 * Shows only the percentage; absolute amounts live in the tooltip.
 * Renders nothing when quota is unavailable (non-portable / error).
 */
export function QuotaBar({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation();
  const [quota, setQuota] = useState<QuotaInfo | null>(null);

  const refresh = useCallback(async () => {
    const next = await getQuota();
    // 瞬态失败不清空：保留上一次成功值，避免进度条闪烁
    if (next) setQuota(next);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    window.addEventListener("focus", refresh);
    window.addEventListener("go-claw:quota-updated", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("go-claw:quota-updated", refresh);
    };
  }, [refresh]);

  if (!quota) return null;

  const percent = Math.min(100, Math.max(0, Math.round(quota.percent)));
  const low = percent < LOW_QUOTA_THRESHOLD;

  if (collapsed) {
    return (
      <Tooltip title={`${t("nav.quota")} ${percent}%`} placement="right">
        <div
          className={styles.quotaRing}
          aria-label={`${t("nav.quota")} ${percent}%`}
        >
          <Progress
            type="circle"
            percent={percent}
            size={32}
            showInfo={false}
            strokeColor={low ? "#ff4d4f" : "#FF4A18"}
          />
        </div>
      </Tooltip>
    );
  }

  return (
    <div className={styles.quotaBar}>
      <div className={styles.quotaBarRow}>
        <span className={styles.quotaBarLabel}>{t("nav.quota")}</span>
        <Progress
          percent={percent}
          size="small"
          showInfo={false}
          strokeColor={low ? "#ff4d4f" : "#FF4A18"}
          className={styles.quotaBarProgress}
        />
        <span
          className={`${styles.quotaBarValue} ${
            low ? styles.quotaBarValueLow : ""
          }`}
        >
          {percent}%
        </span>
      </div>
    </div>
  );
}
