import styles from "./ConsoleLoadingShell.module.less";

interface ConsoleLoadingShellProps {
  label?: string;
}

export default function ConsoleLoadingShell({
  label = "正在加载 GO CLAW…",
}: ConsoleLoadingShellProps) {
  return (
    <main className={styles.page} role="status" aria-live="polite">
      <div className={styles.brand}>
        <img className={styles.logo} src="/go-claw-mark.svg" alt="GO CLAW" />
        <span className={styles.pulse} aria-hidden="true" />
        <p className={styles.label}>{label}</p>
      </div>
    </main>
  );
}
