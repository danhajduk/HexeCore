import { describe, expect, it } from "vitest";

import {
  canShowUninstallAction,
  confirmingUninstallState,
  idleUninstallState,
  uninstallFailureState,
  uninstallSuccessState,
  uninstallingState,
} from "./addonsUninstall";

describe("addons uninstall helpers", () => {
  it("shows uninstall action only for admin", () => {
    expect(canShowUninstallAction(true)).toBe(true);
    expect(canShowUninstallAction(false)).toBe(false);
  });

  it("supports confirmation flow states", () => {
    expect(idleUninstallState().phase).toBe("idle");
    expect(confirmingUninstallState().phase).toBe("confirming");
    expect(uninstallingState().phase).toBe("uninstalling");
    expect(uninstallSuccessState().phase).toBe("success");
    expect(uninstallSuccessState().message).toContain("uninstalled");
  });

  it("maps standalone addon_not_installed to remediation guidance", () => {
    const failed = uninstallFailureState(404, '{"detail":"addon_not_installed"}', "standalone");
    expect(failed.phase).toBe("failed");
    expect(failed.message).toContain("Standalone uninstall");
    expect(failed.remediation).toHaveLength(2);
    expect(failed.remediation[0]).toContain("supervisor");
  });

  it("returns generic failure message for embedded uninstall errors", () => {
    const failed = uninstallFailureState(400, "catalog_http_error:404", "embedded");
    expect(failed.phase).toBe("failed");
    expect(failed.message).toContain("HTTP 400");
    expect(failed.message).toContain("catalog_http_error:404");
    expect(failed.remediation).toHaveLength(0);
  });
});
