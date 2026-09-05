import { Layout, Space, Modal, message } from "antd";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ThemeToggleButton from "../components/ThemeToggleButton";
import { ExternalMarkdownLink } from "../components/Markdown/externalLinkComponents";
import { useTheme } from "../contexts/ThemeContext";
import { useDesktopUpdate } from "../contexts/DesktopUpdateContext";
import { isDesktopApp } from "../tauri/backendRuntime";
import { Slot } from "../plugins/registry/Slot";
import api from "../api";
import { UpdateSection } from "./UpdateSection";
import styles from "./index.module.less";

export default function Header() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const update = useDesktopUpdate();
  const [version, setVersion] = useState("");
  const [open, setOpen] = useState(false);
  const clicks = useRef<number[]>([]);
  useEffect(() => {
    let active = true;
    api
      .getVersion()
      .then((result) => {
        if (active) setVersion(result?.version ?? "");
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  const handleLogoClick = () => {
    if (!isDesktopApp()) return;
    const now = Date.now();
    clicks.current = [
      ...clicks.current.filter((time) => now - time <= 3000),
      now,
    ];
    if (clicks.current.length >= 8) {
      clicks.current = [];
      invoke("open_devtools")
        .then(() => message.success("DevTools opened"))
        .catch(() => message.error("DevTools unavailable"));
    }
  };
  return (
    <>
      <Layout.Header className={styles.header}>
        <div className={styles.logoWrapper}>
          <div onClick={handleLogoClick}>
            <Slot name="header.logo" kind="replace">
              <img
                data-testid="go-claw-header-logo"
                src={
                  isDark
                    ? "/go-claw-horizontal-white.svg"
                    : "/go-claw-horizontal.svg"
                }
                alt="GO CLAW"
                className={styles.logoImg}
              />
            </Slot>
          </div>
          <div className={styles.logoDivider} />
          {version && (
            <button
              type="button"
              data-testid="update-version-trigger"
              className={`${styles.versionBadge} ${styles.versionBadgeClickable}`}
              onClick={() => setOpen(true)}
            >
              v{version}
            </button>
          )}
        </div>
        <Slot name="header.left" kind="fill" />
        <Space size="middle">
          <Slot name="header.right" kind="fill" />
          <div className={styles.headerDivider} />
          <ThemeToggleButton />
        </Space>
      </Layout.Header>
      <Modal
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        title={t("updates.currentVersion") + " · GO CLAW"}
        width={640}
        className={styles.updateModal}
      >
        <UpdateSection />
        {update.status?.latest?.notes && (
          <div className={styles.updateModalBody}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{ a: ExternalMarkdownLink }}
            >
              {update.status.latest.notes}
            </ReactMarkdown>
          </div>
        )}
      </Modal>
    </>
  );
}
