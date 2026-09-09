import { ThunderboltOutlined } from "@ant-design/icons";
import { Tooltip } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { getQuota, type QuotaInfo } from "../api/modules/quota";
import {
  formatComputeBalance,
  formatExactComputeBalance,
  LOW_COMPUTE_THRESHOLD,
} from "./quotaDisplay";
import styles from "./index.module.less";

const POLL_INTERVAL_MS = 60_000;
const CREDIT_FEEDBACK_MS = 3_000;

export function QuotaBar({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [quota, setQuota] = useState<QuotaInfo | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [creditedDelta, setCreditedDelta] = useState<number | null>(null);
  const quotaRef = useRef<QuotaInfo | null>(null);
  const feedbackTimerRef = useRef<number | null>(null);

  const refresh = useCallback(async (announceCredit = false) => {
    const next = await getQuota();
    setLoaded(true);
    if (!next) return;

    const previous = quotaRef.current?.displayRemaining;
    quotaRef.current = next;
    setQuota(next);
    if (
      announceCredit &&
      previous !== undefined &&
      next.displayRemaining !== undefined &&
      next.displayRemaining > previous
    ) {
      setCreditedDelta(next.displayRemaining - previous);
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current);
      }
      feedbackTimerRef.current = window.setTimeout(
        () => setCreditedDelta(null),
        CREDIT_FEEDBACK_MS,
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    const onFocus = () => void refresh();
    const onQuotaUpdated = () => void refresh(true);
    window.addEventListener("focus", onFocus);
    window.addEventListener("go-claw:quota-updated", onQuotaUpdated);
    return () => {
      window.clearInterval(timer);
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current);
      }
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("go-claw:quota-updated", onQuotaUpdated);
    };
  }, [refresh]);

  const openRecharge = () => navigate("/compute-recharge");
  const hasDisplayBalance = quota?.displayRemaining !== undefined;
  const compactBalance = hasDisplayBalance
    ? formatComputeBalance(quota.displayRemaining!)
    : quota
    ? `${Math.min(100, Math.max(0, Math.round(quota.percent)))}%`
    : "--";
  const exactBalance = hasDisplayBalance
    ? formatExactComputeBalance(quota.displayRemaining!)
    : compactBalance;
  const low =
    hasDisplayBalance && quota.displayRemaining! < LOW_COMPUTE_THRESHOLD;
  const status =
    !loaded || !quota
      ? t("quotaDisplay.unavailable")
      : !hasDisplayBalance
      ? t("quotaDisplay.legacy")
      : low
      ? t("quotaDisplay.low")
      : t("quotaDisplay.sufficient");
  const fullLabel = `${t("quotaDisplay.balance")} ${exactBalance} ${t(
    "computeRecharge.units",
  )} · ${status}`;

  if (collapsed) {
    return (
      <Tooltip title={fullLabel} placement="right">
        <button
          type="button"
          className={`${styles.quotaRing} ${low ? styles.quotaLow : ""}`}
          aria-label={fullLabel}
          onClick={openRecharge}
        >
          <ThunderboltOutlined />
          <span className={styles.quotaStatusDot} aria-hidden="true" />
        </button>
      </Tooltip>
    );
  }

  return (
    <div className={`${styles.quotaBar} ${low ? styles.quotaLow : ""}`}>
      <button
        type="button"
        className={styles.quotaBarMain}
        aria-label={fullLabel}
        onClick={openRecharge}
      >
        <span className={styles.quotaBarRow}>
          <span className={styles.quotaBarLabel}>
            {t("quotaDisplay.balance")}
          </span>
          <span
            className={`${styles.quotaBarValue} ${
              low ? styles.quotaBarValueLow : ""
            }`}
          >
            {compactBalance}
          </span>
        </span>
        <span className={styles.quotaBarRow}>
          <span className={styles.quotaStatus}>
            <span className={styles.quotaStatusDot} aria-hidden="true" />
            {status}
          </span>
        </span>
      </button>
      <button
        type="button"
        className={styles.quotaRechargeButton}
        onClick={openRecharge}
      >
        {t("quotaDisplay.recharge")}
      </button>
      {creditedDelta !== null && (
        <span className={styles.quotaCreditFeedback} role="status">
          +{formatComputeBalance(creditedDelta)} {t("quotaDisplay.credited")}
        </span>
      )}
    </div>
  );
}
