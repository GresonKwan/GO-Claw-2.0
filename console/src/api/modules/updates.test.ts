import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { decodeUpdateStatus } from "./updates";

const fixture = JSON.parse(
  readFileSync(
    "../docs/contracts/v2.1.2/fixtures/update-status.valid.json",
    "utf8",
  ),
);

describe("update status contract decoder", () => {
  it("consumes the shared machine fixture without losing byte semantics", () => {
    const state = decodeUpdateStatus(fixture);
    expect(state.progressPercent).toBe(90);
    expect(state.downloaded).toBe(200);
    expect(state.notifyAvailable).toBe(true);
  });
  it.each([
    { schemaVersion: 3 },
    { revision: -1 },
    { downloaded: -1 },
    { progressPercent: NaN },
    { progressPercent: 101 },
    { targetManifestSha256: "not-a-hash" },
    { transactionId: "../../private" },
  ])("rejects invalid or unknown state %j", (change) => {
    expect(() => decodeUpdateStatus({ ...fixture, ...change })).toThrow();
  });
  it("accepts old server status without inventing a transaction", () => {
    const old = decodeUpdateStatus({
      phase: "available",
      currentVersion: "2.1.1",
      latest: fixture.latest,
      downloaded: 0,
      total: null,
      error: "",
      enabled: true,
    });
    expect(old.schemaVersion).toBeUndefined();
    expect(old.transactionId).toBeUndefined();
  });
});
