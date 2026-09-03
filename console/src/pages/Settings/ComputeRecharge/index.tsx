import { Alert, Button, Result, Space, Spin, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import {
  rechargeApi,
  type RechargeBalance,
  type RechargeConfig,
  type RechargeLedgerEntry,
  type RechargeOrder,
} from "../../../api/modules/recharge";
import { AmountCard } from "./components/AmountCard";
import { BalanceCard } from "./components/BalanceCard";
import { LedgerTable } from "./components/LedgerTable";
import { NativePayModal } from "./components/NativePayModal";
import styles from "./index.module.less";

const ORDER_POLL_MS = 2_000;

function newIdempotencyKey(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export default function ComputeRechargePage() {
  const { t } = useTranslation();
  const [config, setConfig] = useState<RechargeConfig | null>(null);
  const [balance, setBalance] = useState<RechargeBalance | null>(null);
  const [ledger, setLedger] = useState<RechargeLedgerEntry[]>([]);
  const [amountFen, setAmountFen] = useState(1_000);
  const [order, setOrder] = useState<RechargeOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const activeConfig = await rechargeApi.config();
      const [activeBalance, activeLedger] = await Promise.all([
        rechargeApi.balance(),
        rechargeApi.ledger(),
      ]);
      if (!mounted.current) return;
      setConfig(activeConfig);
      setBalance(activeBalance);
      setLedger(activeLedger.items);
      setUnavailable(false);
    } catch {
      if (mounted.current) setUnavailable(true);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  useEffect(() => {
    if (
      !order ||
      ["SUCCEEDED", "EXPIRED", "CLOSED", "REVIEW_REQUIRED"].includes(
        order.status,
      )
    ) {
      return undefined;
    }
    let cancelled = false;
    const timer = window.setInterval(() => {
      void rechargeApi
        .order(order.orderId)
        .then((next) => {
          if (cancelled) return;
          setOrder(next);
          if (next.status === "SUCCEEDED") {
            window.dispatchEvent(new Event("go-claw:quota-updated"));
            void load();
          }
        })
        .catch(() => undefined);
    }, ORDER_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [load, order]);

  const submit = async () => {
    if (!config || submitting) return;
    if (amountFen < config.minAmountFen || amountFen > config.maxAmountFen) {
      return;
    }
    setSubmitting(true);
    setSubmitError(false);
    const idempotencyKey = newIdempotencyKey();
    try {
      const created = await rechargeApi.createOrder(
        amountFen,
        config.termsVersion,
        idempotencyKey,
      );
      if (mounted.current) setOrder(created);
    } catch {
      if (mounted.current) setSubmitError(true);
    } finally {
      if (mounted.current) setSubmitting(false);
    }
  };

  const header = (
    <PageHeader
      parent={t("nav.settings")}
      current={t("computeRecharge.title")}
    />
  );
  if (loading) {
    return (
      <div className={styles.container}>
        {header}
        <Spin />
      </div>
    );
  }
  if (unavailable || !config) {
    return (
      <div className={styles.container}>
        {header}
        <Result
          status="info"
          title={t("computeRecharge.initializing")}
          subTitle={t("computeRecharge.initializingHint")}
          extra={
            <Button onClick={() => void load()}>
              {t("common.retry", "Retry")}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {header}
      <div className={styles.content}>
        <Space direction="vertical" size={16} className={styles.fullWidth}>
          <Alert
            type="info"
            showIcon
            message={
              <Typography.Text strong>{config.displayRate}</Typography.Text>
            }
            description={t("computeRecharge.rateHint")}
          />
          {!config.enabled && (
            <Alert
              type="warning"
              showIcon
              message={t("computeRecharge.disabled")}
            />
          )}
          {submitError && (
            <Alert
              type="error"
              showIcon
              message={t("computeRecharge.createFailed")}
            />
          )}
          <div className={styles.grid}>
            <BalanceCard balance={balance} />
            <AmountCard
              config={config}
              amountFen={amountFen}
              submitting={submitting}
              disabled={!config.enabled}
              onAmountChange={setAmountFen}
              onSubmit={() => void submit()}
            />
          </div>
          <Typography.Title level={4}>
            {t("computeRecharge.ledger")}
          </Typography.Title>
          <LedgerTable items={ledger} />
        </Space>
      </div>
      <NativePayModal order={order} onClose={() => setOrder(null)} />
    </div>
  );
}
