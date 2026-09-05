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

  useEffect(() => setRenewal(0), [item?.id, open]);

  useEffect(() => {
    let active = true;
    setUrl("");
    if (!open || !item) return () => undefined;
    deliverablesApi
      .mediaTicket(item.id)
      .then(({ ticket }) => {
        if (active)
          setUrl(deliverablesApi.mediaUrl(item.id, ticket, "content"));
      })
      .catch(() => undefined);
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
      {!url && <div role="status">{t("deliverables.loading")}</div>}
      {url && item?.previewKind === "image" && (
        <img
          src={url}
          alt={item.name}
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
          onError={() => setRenewal((value) => (value < 1 ? value + 1 : value))}
          style={{ display: "block", width: "100%", maxHeight: "76vh" }}
        />
      )}
    </Modal>
  );
}
