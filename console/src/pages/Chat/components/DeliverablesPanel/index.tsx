import { DownOutlined, FileOutlined } from "@ant-design/icons";
import { Button, Dropdown, message } from "antd";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { cloneElement, type ReactElement } from "react";
import type {
  DeliverableItem,
  DeliverablesEnvelope,
} from "@/api/modules/deliverables";
import { deliverablesApi } from "@/api/modules/deliverables";
import ArtifactPreviewDialog from "./ArtifactPreviewDialog";
import MediaDeliverablesRail from "./MediaDeliverablesRail";
import styles from "./index.module.less";

function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DeliverablesPanel({
  envelope,
}: {
  envelope: DeliverablesEnvelope | null;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [preview, setPreview] = useState<DeliverableItem | null>(null);
  const restoreFocus = useRef<HTMLButtonElement | null>(null);
  if (!envelope || envelope.status !== "ready" || envelope.items.length === 0)
    return null;

  const media = envelope.items.filter((item) => item.previewKind);
  const files = envelope.items.filter((item) => !item.previewKind);
  const shown = expanded ? files : files.slice(0, 3);
  const action = async (item: DeliverableItem, kind: "open" | "reveal") => {
    try {
      await deliverablesApi.open(item.id, kind);
    } catch {
      message.error(t("deliverables.openFailed"));
    }
  };

  return (
    <section className={styles.panel} aria-label={t("deliverables.title")}>
      <h3>{t("deliverables.title")}</h3>
      {media.length > 0 && (
        <MediaDeliverablesRail
          items={media}
          onPreview={(item, target) => {
            restoreFocus.current = target;
            setPreview(item);
          }}
          onReveal={(item) => void action(item, "reveal")}
        />
      )}
      {shown.length > 0 && (
        <div className={styles.fileList}>
          {shown.map((item) => (
            <div className={styles.fileRow} key={item.id}>
              <FileOutlined />
              <div className={styles.fileMeta}>
                <span title={item.name}>{item.name}</span>
                <small>
                  {item.exists
                    ? `${item.kind} · ${sizeLabel(item.sizeBytes)}`
                    : t("deliverables.missing")}
                </small>
              </div>
              <Dropdown.Button
                size="small"
                disabled={!item.exists}
                onClick={() => void action(item, "open")}
                buttonsRender={([main, menu]) => [
                  cloneElement(main as ReactElement<Record<string, unknown>>, {
                    disabled: !item.exists || !item.directOpenAllowed,
                    "aria-label": t("deliverables.open"),
                  }),
                  menu,
                ]}
                menu={{
                  items: [
                    {
                      key: "reveal",
                      label: t("deliverables.reveal"),
                      disabled: !item.exists,
                    },
                  ],
                  onClick: () => void action(item, "reveal"),
                }}
              >
                {t("deliverables.open")}
              </Dropdown.Button>
            </div>
          ))}
          {files.length > 3 && (
            <Button
              type="link"
              size="small"
              icon={<DownOutlined />}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded
                ? t("deliverables.collapse")
                : t("deliverables.showMore", { count: files.length - 3 })}
            </Button>
          )}
        </div>
      )}
      <ArtifactPreviewDialog
        item={preview}
        open={preview !== null}
        onClose={() => {
          setPreview(null);
          window.setTimeout(() => restoreFocus.current?.focus(), 0);
        }}
      />
    </section>
  );
}
