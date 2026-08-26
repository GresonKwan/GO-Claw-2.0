import { useState } from "react";
import { Popover } from "antd";
import {
  SparkMenuExpandLine,
  SparkMenuFoldLine,
  SparkSettingLine,
} from "@agentscope-ai/icons";
import { useTranslation } from "react-i18next";
import { QuotaBar } from "./QuotaBar";
import SidebarSettingsPanel from "./SidebarSettingsPanel";
import styles from "./index.module.less";

interface SidebarBottomDockProps {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

export function SidebarBottomDock({
  collapsed,
  onCollapsedChange,
}: SidebarBottomDockProps) {
  const { t } = useTranslation();
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className={styles.sidebarBottomDock} data-testid="sidebar-bottom-dock">
      <div className={styles.dockQuota} data-dock-order="quota">
        <QuotaBar collapsed={collapsed} />
      </div>
      <div className={styles.dockActionRow} data-dock-order="actions">
        <Popover
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          placement="topRight"
          trigger="click"
          content={
            <SidebarSettingsPanel onClose={() => setSettingsOpen(false)} />
          }
        >
          <button
            type="button"
            className={`${styles.dockAction} ${styles.dockSettingsAction}`}
            aria-label={t("nav.settings")}
          >
            <SparkSettingLine size={20} />
            {!collapsed && <span>{t("nav.settings")}</span>}
          </button>
        </Popover>
        <button
          type="button"
          className={`${styles.dockAction} ${styles.dockCollapseAction}`}
          aria-label={collapsed ? t("sidebar.expand") : t("sidebar.collapse")}
          onClick={() => onCollapsedChange(!collapsed)}
        >
          {collapsed ? (
            <SparkMenuExpandLine size={22} />
          ) : (
            <SparkMenuFoldLine size={22} />
          )}
        </button>
      </div>
    </div>
  );
}
