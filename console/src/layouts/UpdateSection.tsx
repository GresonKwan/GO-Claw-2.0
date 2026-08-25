import { useCallback, useEffect, useState } from "react";
import { Button, Modal, Progress, Spin, Tag } from "antd";
import { useTranslation } from "react-i18next";
import {
  updatesApi,
  type ReleaseItem,
  type UpdateStatus,
} from "../api/modules/updates";
import styles from "./index.module.less";

const POLL_MS = 10_000;

/** 齿轮弹层中的"版本与更新"区块（便携浏览器模式，走后端 HTTP）。 */
export function UpdateSection() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [checking, setChecking] = useState(false);

  const refresh = useCallback(async () => {
    setStatus(await updatesApi.status());
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!status) return null; // 非便携 / updates 关闭：整体隐藏

  const busy = ["checking", "downloading", "installing"].includes(status.phase);
  const hasUpdate = Boolean(status.latest?.isNewer);
  const percent =
    status.total && status.total > 0
      ? Math.round((status.downloaded / status.total) * 100)
      : undefined;

  const doCheck = async () => {
    setChecking(true);
    setStatus(await updatesApi.check());
    setChecking(false);
  };

  const doDownload = async () => {
    setStatus(await updatesApi.download());
  };

  const doInstall = () => {
    Modal.confirm({
      title: t("updates.installConfirmTitle"),
      content: t("updates.installConfirmContent", {
        version: status.latest?.version,
      }),
      okText: t("updates.installNow"),
      cancelText: t("common.cancel"),
      onOk: async () => {
        setStatus(await updatesApi.install());
      },
    });
  };

  const loadHistory = async () => {
    if (!showHistory) {
      const data = await updatesApi.releases();
      setReleases(data?.releases ?? []);
    }
    setShowHistory(!showHistory);
  };

  return (
    <div className={styles.updateSection}>
      <div className={styles.updateRow}>
        <span>
          {t("updates.currentVersion")}: v{status.currentVersion}
        </span>
        <Button size="small" loading={checking} onClick={doCheck}>
          {t("updates.checkNow")}
        </Button>
      </div>

      {status.phase === "failed" && status.error && (
        <div className={styles.updateError}>{t("updates.checkFailed")}</div>
      )}

      {hasUpdate && (
        <div className={styles.updateRow}>
          <Tag color="orange">
            {t("updates.newVersion", { version: status.latest?.version })}
          </Tag>
        </div>
      )}

      {status.phase === "available" && (
        <Button type="primary" size="small" block onClick={doDownload}>
          {t("updates.downloadNow")}
        </Button>
      )}

      {status.phase === "downloading" && (
        <Progress
          percent={percent}
          size="small"
          status="active"
          showInfo={percent !== undefined}
        />
      )}

      {status.phase === "downloaded" && (
        <Button
          type="primary"
          size="small"
          block
          loading={busy}
          onClick={doInstall}
        >
          {t("updates.installNow")}
        </Button>
      )}

      {status.phase === "installing" && (
        <div className={styles.updateRow}>
          <Spin size="small" /> {t("updates.installing")}
        </div>
      )}

      <Button type="link" size="small" onClick={loadHistory}>
        {showHistory ? t("updates.hideHistory") : t("updates.showHistory")}
      </Button>
      {showHistory && (
        <div className={styles.updateHistory}>
          {releases.length === 0 && <div>{t("updates.historyEmpty")}</div>}
          {releases.map((r) => (
            <div key={r.version} className={styles.updateHistoryItem}>
              <span>
                v{r.version}
                {r.isCurrent && (
                  <Tag color="green">{t("updates.currentTag")}</Tag>
                )}
              </span>
              {!r.isCurrent && r.setupUrl && r.signatureUrl && (
                <Button
                  size="small"
                  type="link"
                  onClick={() =>
                    Modal.confirm({
                      title: t("updates.installConfirmTitle"),
                      content: t("updates.installConfirmContent", {
                        version: r.version,
                      }),
                      okText: t("updates.installNow"),
                      cancelText: t("common.cancel"),
                      onOk: async () => {
                        setStatus(
                          await updatesApi.installVersion(
                            r.version,
                            r.setupUrl,
                            r.signatureUrl,
                          ),
                        );
                      },
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
