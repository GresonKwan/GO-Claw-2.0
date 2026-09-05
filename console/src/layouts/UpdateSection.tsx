import { useState } from "react";
import { Button, Modal, Progress } from "antd";
import { useTranslation } from "react-i18next";
import { updatesApi, type ReleaseItem } from "../api/modules/updates";
import {
  useDesktopUpdate,
  updateErrorCode,
} from "../contexts/DesktopUpdateContext";
import styles from "./index.module.less";

/** One shared update state, no widget timers or independent download channel. */
export function UpdateSection() {
  const { t } = useTranslation();
  const update = useDesktopUpdate();
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const status = update.status;
  if (!status?.enabled) return null;
  const busy =
    update.actionPending ||
    ["checking", "downloading", "installing"].includes(status.phase);
  const progress =
    status.schemaVersion === 2
      ? status.progressPercent
      : status.phase === "downloaded" || status.phase === "installing"
      ? 90
      : status.total
      ? Math.min(85, (status.downloaded / status.total) * 85)
      : null;
  const showProgress =
    progress != null &&
    ["downloading", "downloaded", "installing", "failed"].includes(
      status.phase,
    );
  const code = update.error || status.error || historyError;
  const confirmInstall = () =>
    Modal.confirm({
      title: t("updates.installConfirmTitle"),
      content: t("updates.installConfirmContent", {
        version: status.latest?.version,
      }),
      okText: t("updates.installNow"),
      cancelText: t("common.cancel"),
      onOk: () => update.install(status),
    });
  const loadHistory = async () => {
    if (!showHistory) {
      try {
        setHistoryError(null);
        setReleases((await updatesApi.releases()).releases);
      } catch (error) {
        setHistoryError(updateErrorCode(error));
      }
    }
    setShowHistory(!showHistory);
  };
  return (
    <div className={styles.updateSection}>
      <div className={styles.updateRow}>
        <span>
          {t("updates.currentVersion")}: v{status.currentVersion}
        </span>
        <span className={styles.updateDotAnchor}>
          <Button
            size="small"
            disabled={busy}
            loading={status.phase === "checking"}
            onClick={() => void update.check()}
          >
            {t("updates.checkNow")}
          </Button>
          {update.notifyAvailable && (
            <span
              aria-hidden="true"
              data-testid="check-update-dot"
              className={styles.updateOrangeDot}
            />
          )}
        </span>
      </div>
      {status.latest?.isNewer && (
        <div className={styles.updateRow}>
          {t("updates.newVersion", { version: status.latest.version })}
        </div>
      )}
      {code && (
        <div role="status" className={styles.updateError}>
          {t("updates.checkFailed")} · {code}
        </div>
      )}
      {showProgress && (
        <Progress
          percent={Math.round(progress!)}
          size="small"
          status={status.phase === "failed" ? "exception" : "active"}
        />
      )}
      {status.enginePhase === "ROLLING_BACK" && (
        <div role="status">{t("updates.recovering", "恢复旧版本")}</div>
      )}
      {(status.phase === "available" ||
        (status.phase === "failed" &&
          status.latest?.isNewer &&
          !status.installationStarted &&
          status.enginePhase !== "BLOCKED")) && (
        <Button
          type="primary"
          size="small"
          block
          disabled={busy}
          onClick={() => void update.download(status)}
        >
          {t("updates.downloadNow")}
        </Button>
      )}
      {status.phase === "downloaded" && (
        <Button
          type="primary"
          size="small"
          block
          loading={update.actionPending}
          onClick={confirmInstall}
        >
          {t("updates.installNow")}
        </Button>
      )}
      {status.phase === "installing" && (
        <div role="status">{t("updates.installing")}</div>
      )}
      <Button
        type="link"
        size="small"
        disabled={busy}
        onClick={() => void loadHistory()}
      >
        {showHistory ? t("updates.hideHistory") : t("updates.showHistory")}
      </Button>
      {showHistory && (
        <div className={styles.updateHistory}>
          {!releases.length && !historyError && (
            <div>{t("updates.historyEmpty")}</div>
          )}
          {releases.map((release) => (
            <div key={release.version} className={styles.updateHistoryItem}>
              <span>
                v{release.version}
                {release.isCurrent ? " · " + t("updates.currentTag") : ""}
              </span>
              {!release.isCurrent &&
                release.setupUrl &&
                release.signatureUrl && (
                  <Button
                    size="small"
                    type="link"
                    disabled={busy}
                    onClick={() =>
                      Modal.confirm({
                        title: t("updates.installConfirmTitle"),
                        content: t("updates.installConfirmContent", {
                          version: release.version,
                        }),
                        okText: t("updates.installNow"),
                        cancelText: t("common.cancel"),
                        onOk: () =>
                          update.installVersion(
                            release.version,
                            release.setupUrl,
                            release.signatureUrl,
                          ),
                      })
                    }
                  >
                    {t("updates.installThisVersion")}
                  </Button>
                )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
