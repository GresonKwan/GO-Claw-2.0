import { Alert, Modal, Spin, Typography } from "antd";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { RechargeOrder } from "../../../../api/modules/recharge";
import styles from "../index.module.less";

export function NativePayModal({
  order,
  onClose,
}: {
  order: RechargeOrder | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [qr, setQr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setQr(null);
    if (!order?.codeUrl?.startsWith("weixin://")) return () => undefined;
    void QRCode.toDataURL(order.codeUrl, {
      width: 260,
      margin: 2,
      errorCorrectionLevel: "M",
    }).then((value) => {
      if (active) setQr(value);
    });
    return () => {
      active = false;
    };
  }, [order?.codeUrl]);

  const status = order?.status;
  return (
    <Modal
      open={Boolean(order)}
      title={t("computeRecharge.scanTitle")}
      footer={null}
      onCancel={onClose}
      destroyOnClose
    >
      <div className={styles.qrArea}>
        {status === "CREDITING" ? (
          <Alert
            type="info"
            showIcon
            message={t("computeRecharge.crediting")}
          />
        ) : status === "SUCCEEDED" ? (
          <Alert
            type="success"
            showIcon
            message={t("computeRecharge.succeeded")}
          />
        ) : qr ? (
          <img
            src={qr}
            alt={t("computeRecharge.qrAlt")}
            width={260}
            height={260}
          />
        ) : (
          <Spin />
        )}
        <Typography.Text>
          ￥{order?.amountCny} · {order?.computeUnits.toLocaleString()}{" "}
          {t("computeRecharge.units")}
        </Typography.Text>
      </div>
    </Modal>
  );
}
