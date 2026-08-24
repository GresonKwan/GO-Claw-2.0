/**
 * builtinMenu.test.ts — GO CLAW customer build hides over-technical entries.
 */
import { describe, it, expect } from "vitest";
import { BUILTIN_MENU } from "./builtinMenu";

const HIDDEN = [
  "core.tools",
  "core.mcp",
  "core.acp",
  "core.heartbeat",
  "core.environments",
  "core.security",
  "core.token-usage",
  "core.backups",
  "core.voice-transcription",
  "core.debug",
  "core.plugin-manager",
];

const KEPT = [
  "core.inbox",
  "core.cron-jobs",
  "core.workspace",
  "core.skills",
  "core.agent-stats",
];

describe("GO CLAW customer menu", () => {
  it("hides over-technical and low-frequency entries", () => {
    for (const id of HIDDEN) {
      const item = BUILTIN_MENU.find((i) => i.id === id);
      expect(item, `${id} should still be declared`).toBeDefined();
      expect(
        item?.visible?.(),
        `${id} should be hidden from the sidebar`,
      ).toBe(false);
    }
  });

  it("keeps customer-facing entries visible", () => {
    for (const id of KEPT) {
      const item = BUILTIN_MENU.find((i) => i.id === id);
      expect(item, `${id} missing from menu`).toBeDefined();
      expect(item?.visible?.() ?? true, `${id} should stay visible`).toBe(
        true,
      );
    }
  });
});
