import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import styles from "./tauri/BackendLoadingPage.module.less";
import BackendLoadingPage from "./tauri/BackendLoadingPage";

vi.mock("./contexts/ThemeContext", () => ({
  useTheme: () => ({ isDark: true }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
  }),
}));

describe("BackendLoadingPage", () => {
  it("stacks the GO CLAW logo above the dashboard progress", () => {
    render(<BackendLoadingPage status="checking" elapsed={3} totalSec={60} />);

    const logo = screen.getByAltText("GO CLAW");
    const progress = screen.getByRole("progressbar");
    expect(logo.parentElement).toBe(progress.parentElement);
    expect(logo.parentElement).toHaveClass(styles.visualStack);
    expect(logo.compareDocumentPosition(progress)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
});
