import { Button, Card, Checkbox, InputNumber, Space, Typography } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { RechargeConfig } from "../../../../api/modules/recharge";
import styles from "../index.module.less";

interface Props {
  config: RechargeConfig;
  amountFen: number;
  submitting: boolean;
  disabled: boolean;
  onAmountChange: (amountFen: number) => void;
  onSubmit: () => void;
}

export function AmountCard({
  config,
  amountFen,
  submitting,
  disabled,
  onAmountChange,
  onSubmit,
}: Props) {
  const { t } = useTranslation();
  const [accepted, setAccepted] = useState(false);
  return (
    <Card className={styles.card} title={t("computeRecharge.chooseAmount")}>
      <Space wrap className={styles.presets}>
        {config.presetsFen.map((preset) => (
          <Button key={preset} onClick={() => onAmountChange(preset)}>
            ￥{preset / 100}
          </Button>
        ))}
      </Space>
      <div className={styles.amountRow}>
        <InputNumber
          aria-label={t("computeRecharge.customAmount")}
          addonBefore="￥"
          min={config.minAmountFen / 100}
          max={config.maxAmountFen / 100}
          precision={2}
          step={0.01}
          value={amountFen / 100}
          onChange={(value) =>
            onAmountChange(Math.round(Number(value ?? 0) * 100))
          }
        />
        <Button
          type="primary"
          loading={submitting}
          disabled={disabled || !accepted}
          onClick={onSubmit}
        >
          {t("computeRecharge.pay")}
        </Button>
      </div>
      <Typography.Text type="secondary">
        {t("computeRecharge.willReceive", {
          units: (amountFen * config.computeUnitsPerFen).toLocaleString(),
        })}
      </Typography.Text>
      <div className={styles.termsRow}>
        <Checkbox
          checked={accepted}
          onChange={(event) => setAccepted(event.target.checked)}
        >
          {t("computeRecharge.acceptTerms", { version: config.termsVersion })}
        </Checkbox>
      </div>
      <Typography.Paragraph type="secondary">
        {t("computeRecharge.dailyLimit", {
          amount: (config.dailyLimitFen / 100).toLocaleString(),
        })}
        {" · "}
        {t("computeRecharge.refundAndInvoice")}
      </Typography.Paragraph>
    </Card>
  );
}
