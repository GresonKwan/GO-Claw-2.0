import React from "react";
import { useTranslation } from "react-i18next";

import { SunMoon } from "lucide-react";
import { Select } from "antd";
import {
  SparkSunLine,
  SparkMoonLine,
  SparkFullscreenLine,
  SparkExitFullscreenLine,
} from "@agentscope-ai/icons";
import { useTheme, type ThemeMode } from "../contexts/ThemeContext";
import { useSidebarModeStore } from "../stores/sidebarModeStore";
import { UpdateSection } from "./UpdateSection";
import { isTauriRuntime } from "../tauri/backendRuntime";
import {
  clearRememberedCloseAction,
  getRememberedCloseAction,
  setRememberedCloseAction,
  type CloseAction,
} from "../tauri/closeWindowPreference";
import styles from "./sidebarSettingsPanel.module.less";

type CloseBehavior = "ask" | CloseAction;

// ── Language config ────────────────────────────────────────────────────────

// ── Component ─────────────────────────────────────────────────────────────

interface SidebarSettingsPanelProps {
  onClose?: () => void;
}

export default function SidebarSettingsPanel({
  onClose,
}: SidebarSettingsPanelProps) {
  const { t } = useTranslation();
  const { themeMode, setThemeMode } = useTheme();
  const { mode: sidebarMode, toggleMode: toggleSidebarMode } =
    useSidebarModeStore();
  const [closeBehavior, setCloseBehavior] = React.useState<CloseBehavior>(() =>
    isTauriRuntime() ? getRememberedCloseAction() ?? "ask" : "ask",
  );

  const changeCloseBehavior = (value: CloseBehavior) => {
    if (value === "ask") {
      clearRememberedCloseAction();
    } else {
      setRememberedCloseAction(value);
    }
    setCloseBehavior(value);
  };

  const themeOptions: {
    key: ThemeMode;
    label: string;
    icon: React.ReactNode;
  }[] = [
    {
      key: "light",
      label: t("theme.light", "Light"),
      icon: <SparkSunLine size={14} />,
    },
    {
      key: "dark",
      label: t("theme.dark", "Dark"),
      icon: <SparkMoonLine size={14} />,
    },
    {
      key: "system",
      label: t("theme.system", "System"),
      icon: <SunMoon size={14} />,
    },
  ];

  return (
    <div className={styles.panel}>
      {/* ── Language ─────────────────────────────────────── */}
      {/* ── Theme ────────────────────────────────────────── */}
      <div className={styles.row}>
        <span className={styles.label}>
          {t("sidebar.settings.theme", "Theme")}
        </span>
        <div className={styles.options}>
          {themeOptions.map(({ key, label, icon }) => (
            <button
              key={key}
              title={label}
              className={`${styles.optBtn} ${
                themeMode === key ? styles.optBtnActive : ""
              }`}
              onClick={() => setThemeMode(key)}
            >
              {icon}
              <span className={styles.optLabel}>{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Close Window (desktop only) ──────────────────── */}
      {isTauriRuntime() ? (
        <div className={styles.row}>
          <span className={styles.label}>
            {t("desktop.closeWindow.preference", "Close Window")}
          </span>
          <Select<CloseBehavior>
            size="small"
            style={{ width: "100%" }}
            value={closeBehavior}
            onChange={changeCloseBehavior}
            options={[
              {
                value: "ask",
                label: t("desktop.closeWindow.askEveryTime", "Ask every time"),
              },
              {
                value: "minimize-to-tray",
                label: t(
                  "desktop.closeWindow.minimizeToTray",
                  "Minimize to Tray",
                ),
              },
              {
                value: "quit",
                label: t("desktop.closeWindow.quitApp", "Quit App"),
              },
            ]}
          />
        </div>
      ) : null}

      {/* ── Mode ─────────────────────────────────────────── */}
      <div className={styles.row}>
        <span className={styles.label}>
          {t("sidebar.settings.mode", "Mode")}
        </span>
        <button
          className={`${styles.optBtn} ${styles.optBtnBlock}`}
          onClick={() => {
            toggleSidebarMode();
            onClose?.();
          }}
        >
          {sidebarMode === "simple" ? (
            <>
              <SparkFullscreenLine size={14} />
              <span className={styles.optLabel}>
                {t("sidebar.fullMode", "Full Mode")}
              </span>
            </>
          ) : (
            <>
              <SparkExitFullscreenLine size={14} />
              <span className={styles.optLabel}>
                {t("sidebar.simpleMode", "Simple Mode")}
              </span>
            </>
          )}
        </button>
      </div>
      <UpdateSection />
    </div>
  );
}
