import { describe, expect, it } from "vitest";

import {
  buildSupervisorUpdateStartPayload,
  preferredSupervisorUpdateMode,
  supervisorLastUpdateError,
  supervisorUpdateStateLabel,
  updateModesForSupervisor,
  type SupervisorUpdateStatus,
} from "./SettingsSupervisor";

describe("SettingsSupervisor update helpers", () => {
  it("offers only advertised modes for online supervisors", () => {
    const status: SupervisorUpdateStatus = { supported_modes: ["git", "core_host", "ssh"] };

    expect(updateModesForSupervisor({ supervisor_id: "sup-1", freshness_state: "online" }, status)).toEqual([
      "git",
      "core_host",
    ]);
    expect(updateModesForSupervisor({ supervisor_id: "sup-1", freshness_state: "stale" }, status)).toEqual([]);
  });

  it("prefers core_host when both update modes are available", () => {
    expect(preferredSupervisorUpdateMode(["git", "core_host"])).toBe("core_host");
    expect(preferredSupervisorUpdateMode(["git"])).toBe("git");
    expect(preferredSupervisorUpdateMode([])).toBeNull();
  });

  it("builds bounded update request payloads", () => {
    expect(buildSupervisorUpdateStartPayload("git", "key-1234")).toEqual({
      source_mode: "git",
      idempotency_key: "key-1234",
      service_update: false,
    });
    expect(buildSupervisorUpdateStartPayload("core_host", "key-1234")).toEqual({
      source_mode: "core_host",
      idempotency_key: "key-1234",
      service_update: true,
    });
  });

  it("labels update state and sanitized last errors from status", () => {
    const status: SupervisorUpdateStatus = {
      update_state: "failed",
      last_update: { state: "failed", error: "[REDACTED]" },
    };

    expect(supervisorUpdateStateLabel(status)).toBe("Failed");
    expect(supervisorLastUpdateError(status)).toBe("[REDACTED]");
  });
});
