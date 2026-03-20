import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { API_BASE } from "./api/client";

export const DEFAULT_PLATFORM_NAME = "Hexe AI";
export const DEFAULT_PLATFORM_SHORT = "Hexe";
export const DEFAULT_PLATFORM_DOMAIN = "hexe-ai.com";
export const DEFAULT_PLATFORM_CONTROL_PLANE_NAME = "Hexe Core";

export type PlatformBranding = {
  platformName: string;
  platformShort: string;
  platformDomain: string;
  coreName: string;
};

const DEFAULT_BRANDING: PlatformBranding = {
  platformName: DEFAULT_PLATFORM_NAME,
  platformShort: DEFAULT_PLATFORM_SHORT,
  platformDomain: DEFAULT_PLATFORM_DOMAIN,
  coreName: DEFAULT_PLATFORM_CONTROL_PLANE_NAME,
};

const PlatformBrandingContext = createContext<PlatformBranding>(DEFAULT_BRANDING);

function readText(value: unknown, fallback: string): string {
  const text = String(value || "").trim();
  return text || fallback;
}

export function PlatformBrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState<PlatformBranding>(DEFAULT_BRANDING);

  useEffect(() => {
    let cancelled = false;

    async function loadBranding() {
      try {
        const res = await fetch(`${API_BASE}/api/system/platform`, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = (await res.json()) as Record<string, unknown>;
        if (cancelled) return;
        setBranding({
          platformName: readText(payload.platform_name, DEFAULT_PLATFORM_NAME),
          platformShort: readText(payload.platform_short, DEFAULT_PLATFORM_SHORT),
          platformDomain: readText(payload.platform_domain, DEFAULT_PLATFORM_DOMAIN),
          coreName: readText(payload.core_name, DEFAULT_PLATFORM_CONTROL_PLANE_NAME),
        });
      } catch {
        if (!cancelled) {
          setBranding(DEFAULT_BRANDING);
        }
      }
    }

    void loadBranding();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    document.title = branding.coreName;
  }, [branding.coreName]);

  return <PlatformBrandingContext.Provider value={branding}>{children}</PlatformBrandingContext.Provider>;
}

export function usePlatformBranding(): PlatformBranding {
  return useContext(PlatformBrandingContext);
}
