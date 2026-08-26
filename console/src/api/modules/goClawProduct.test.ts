import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "../request";
import { goClawProductApi } from "./goClawProduct";

vi.mock("../request", () => ({ request: vi.fn() }));

describe("goClawProductApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("gets an employee tier using the public query contract", async () => {
    await goClawProductApi.getModelTier("employee / 1");
    expect(request).toHaveBeenCalledWith(
      "/go-claw/model-tier?agent_id=employee%20%2F%201",
    );
  });

  it("sets only schema, employee and tier fields", async () => {
    const body = {
      schemaVersion: 1 as const,
      agentId: "employee-1",
      tier: "performance" as const,
    };
    await goClawProductApi.setModelTier(body);
    expect(request).toHaveBeenCalledWith("/go-claw/model-tier", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  });
});
