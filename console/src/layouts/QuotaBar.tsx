import { useCallback, useEffect, useState } from "react";
import { Progress } from "antd";
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
export function QuotaBar() {
  const { t } = useTranslation();
  const [quota, setQuota] = useState<QuotaInfo | null>(null);

  const refresh = useCallback(async () => {
    setQuota(await getQuota());
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [refresh]);

  if (!quota) return null;

  const percent = Math.min(100, Math.max(0, Math.round(quota.percent)));
  const low = percent < LOW_QUOTA_THRESHOLD;

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
