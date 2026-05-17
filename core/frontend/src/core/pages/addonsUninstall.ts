export type UninstallPhase = "idle" | "confirming" | "uninstalling" | "success" | "failed";

export type UninstallViewState = {
  phase: UninstallPhase;
  message: string | null;
  remediation: string[];
};

export type AddonRuntimeKind = "embedded" | "standalone";

export function canShowUninstallAction(isAdmin: boolean): boolean {
  return isAdmin;
}

export function idleUninstallState(): UninstallViewState {
  return {
    phase: "idle",
    message: null,
    remediation: [],
  };
}

export function confirmingUninstallState(): UninstallViewState {
  return {
    phase: "confirming",
    message: null,
    remediation: [],
  };
}

export function uninstallingState(): UninstallViewState {
  return {
    phase: "uninstalling",
    message: null,
    remediation: [],
  };
}

export function uninstallSuccessState(): UninstallViewState {
  return {
    phase: "success",
    message: "Addon uninstalled.",
    remediation: [],
  };
}

function parseDetail(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "install_failed";
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail.trim();
    if (parsed.detail && typeof parsed.detail === "object") {
      const typed = parsed.detail as { error?: unknown; code?: unknown; message?: unknown };
      if (typeof typed.error === "string" && typed.error.trim()) return typed.error.trim();
      if (typeof typed.code === "string" && typed.code.trim()) return typed.code.trim();
      if (typeof typed.message === "string" && typed.message.trim()) return typed.message.trim();
    }
  } catch {
    // Non-JSON payloads are handled by plain-text fallback.
  }
  return trimmed;
}

export function uninstallFailureState(status: number, raw: string, runtimeKind: AddonRuntimeKind): UninstallViewState {
  const detail = parseDetail(raw);
  if (status === 401) {
    return {
      phase: "failed",
      message: "Unauthorized: admin session required for uninstall.",
      remediation: ["Sign in as admin and retry uninstall."],
    };
  }

  if (detail === "addon_not_installed" && runtimeKind === "standalone") {
    return {
      phase: "failed",
      message: "Standalone uninstall is not automated by /api/store/uninstall.",
      remediation: [
        "Stop the standalone service using the supervisor desired/runtime workflow.",
        "Remove standalone service files according to docs/standalone-addon.md.",
      ],
    };
  }

  return {
    phase: "failed",
    message: `Uninstall failed (HTTP ${status}): ${detail}`,
    remediation: [],
  };
}
