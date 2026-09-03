import { Card, Progress, Statistic } from "antd";
import { useTranslation } from "react-i18next";
import type { RechargeBalance } from "../../../../api/modules/recharge";
import styles from "../index.module.less";

export function BalanceCard({ balance }: { balance: RechargeBalance | null }) {
  const { t } = useTranslation();
  return (
    <Card className={styles.card} loading={!balance}>
      <Statistic
        title={t("computeRecharge.remaining")}
        value={balance?.remainingComputeUnits ?? 0}
        formatter={(value) => Number(value).toLocaleString()}
        suffix={t("computeRecharge.units")}
      />
      <Progress percent={balance?.percent ?? 0} strokeColor="#ff4a18" />
    </Card>
  );
}
