import { Table, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { RechargeLedgerEntry } from "../../../../api/modules/recharge";

export function LedgerTable({ items }: { items: RechargeLedgerEntry[] }) {
  const { t } = useTranslation();
  return (
    <Table
      rowKey="entryId"
      pagination={false}
      locale={{ emptyText: t("computeRecharge.noLedger") }}
      dataSource={items}
      columns={[
        {
          title: t("computeRecharge.time"),
          dataIndex: "occurredAt",
          render: (value: string) => new Date(value).toLocaleString(),
        },
        {
          title: t("computeRecharge.kind"),
          dataIndex: "kind",
          render: (value: string) => <Tag>{value}</Tag>,
        },
        {
          title: t("computeRecharge.amount"),
          dataIndex: "amountFen",
          render: (value: number) => `￥${(value / 100).toFixed(2)}`,
        },
        {
          title: t("computeRecharge.computeUnits"),
          dataIndex: "computeUnits",
          render: (value: number) => value.toLocaleString(),
        },
      ]}
    />
  );
}
