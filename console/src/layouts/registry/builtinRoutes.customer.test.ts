import { describe, expect, it, vi } from "vitest";
import { BUILTIN_ROUTES } from "./builtinRoutes";

vi.mock("../../pages/Chat", () => ({ default: () => null }));
vi.mock("../../pages/Coding", () => ({ default: () => null }));

describe("GO CLAW customer routes", () => {
  it("does not export hidden customer deep links", () => {
    const ids = new Set(BUILTIN_ROUTES.map((route) => route.id));
    expect(ids.has("core.workspace")).toBe(false);
    expect(ids.has("core.agent-stats")).toBe(false);
    expect(ids.has("core.models")).toBe(false);
  });
});
