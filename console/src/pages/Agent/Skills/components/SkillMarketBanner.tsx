import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@agentscope-ai/design";
import styles from "../index.module.less";

export function SkillMarketBanner({ onBrowse }: { onBrowse: () => void }) {
  const { t } = useTranslation();
  const titleId = useId();

  return (
    <section className={styles.marketBanner} aria-labelledby={titleId}>
      <div className={styles.marketBannerCopy}>
        <h2 id={titleId}>{t("skills.marketBannerTitle")}</h2>
        <p>{t("skills.marketBannerDescription")}</p>
      </div>
      <Button
        type="primary"
        className={styles.marketBannerButton}
        onClick={onBrowse}
      >
        {t("skills.marketBannerBrowse")}
      </Button>
    </section>
  );
}
