import { Modal } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  deliverablesApi,
  type DeliverableItem,
} from "@/api/modules/deliverables";

export default function ArtifactPreviewDialog({
  item,
  open,
  onClose,
}: {
  item: DeliverableItem | null;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [renewal, setRenewal] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setRenewal(0);
    setFailed(false);
  }, [item?.id, open]);

  useEffect(() => {
    let active = true;
    setUrl("");
    setFailed(false);
    if (!open || !item) return () => undefined;
    deliverablesApi
      .mediaTicket(item.id)
      .then(({ ticket }) => {
        if (active)
          setUrl(deliverablesApi.mediaUrl(item.id, ticket, "content"));
      })
      .catch(() => {
        if (!active) return;
        if (renewal < 1) {
          setRenewal((value) => Math.min(1, value + 1));
        } else {
          setFailed(true);
        }
      });
    return () => {
      active = false;
    };
  }, [item, open, renewal]);

  return (
    <Modal
      open={open}
      title={item?.name}
      footer={null}
      onCancel={onClose}
      destroyOnHidden
      width="min(92vw, 1080px)"
      centered
    >
      {!url && !failed && <div role="status">{t("deliverables.loading")}</div>}
      {failed && <div role="status">{t("deliverables.previewFailed")}</div>}
      {url && item?.previewKind === "image" && (
        <img
          src={url}
          alt={item.name}
          onError={() => {
            if (renewal < 1) setRenewal(renewal + 1);
            else {
              setUrl("");
              setFailed(true);
            }
          }}
          style={{
            display: "block",
            maxWidth: "100%",
            maxHeight: "76vh",
            margin: "auto",
          }}
        />
      )}
      {url && item?.previewKind === "video" && (
        <video
          src={url}
          aria-label={item.name}
          controls
          autoPlay
          onError={() => {
            if (renewal < 1) setRenewal(renewal + 1);
            else {
              setUrl("");
              setFailed(true);
            }
          }}
          style={{ display: "block", width: "100%", maxHeight: "76vh" }}
        />
      )}
    </Modal>
  );
}
