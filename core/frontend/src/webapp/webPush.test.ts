import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({ api: vi.fn() }));
import { api } from "./api";
import { enableWebPush } from "./webPush";

describe("web push lifecycle", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    Object.defineProperty(globalThis, "window", { configurable: true, value: globalThis });
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: { serviceWorker: {} } });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    Object.defineProperty(window, "PushManager", { configurable: true, value: function PushManager() {} });
  });

  it("stops when notification permission is denied", async () => {
    Object.defineProperty(window, "Notification", { configurable: true, value: { requestPermission: vi.fn().mockResolvedValue("denied") } });
    await expect(enableWebPush("device-1")).rejects.toThrow("notification_permission_denied");
    expect(api).not.toHaveBeenCalled();
  });

  it("sends raw subscription only to the gateway and stores its opaque reference in Core", async () => {
    Object.defineProperty(window, "Notification", { configurable: true, value: { requestPermission: vi.fn().mockResolvedValue("granted") } });
    const subscription = { toJSON: () => ({ endpoint: "https://provider.example/private", keys: { p256dh: "key", auth: "auth" } }), unsubscribe: vi.fn() };
    const pushManager = { getSubscription: vi.fn().mockResolvedValue(null), subscribe: vi.fn().mockResolvedValue(subscription) };
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { ready: Promise.resolve({ pushManager }) } });
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/config")) return { configured: true, gateway_url: "https://gateway.example/v1/subscriptions", gateway_audience: "gateway", vapid_public_key: "AQID" } as never;
      if (path.endsWith("/grants")) return { contract_version: "hexe.web-push-registration.v1", grant: "signed-grant", gateway_url: "https://gateway.example/v1/subscriptions", gateway_audience: "gateway" } as never;
      return { ok: true } as never;
    });
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ subscription_ref: "opaque_ref_123" }) }) as never;
    await enableWebPush("device-1");
    expect(fetch).toHaveBeenCalledWith("https://gateway.example/v1/subscriptions", expect.objectContaining({ credentials: "omit" }));
    const gatewayBody = JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body));
    expect(gatewayBody.subscription.endpoint).toBe("https://provider.example/private");
    const coreWrite = vi.mocked(api).mock.calls.find(([path]) => String(path).includes("/api/auth/devices/"));
    expect(String(coreWrite?.[1]?.body)).toContain("opaque_ref_123");
    expect(String(coreWrite?.[1]?.body)).not.toContain("provider.example");
  });
});
