import { api } from "./api";

type PushConfig = {
  configured: boolean;
  gateway_url: string | null;
  gateway_audience: string;
  vapid_public_key: string | null;
};

type Grant = {
  contract_version: string;
  grant: string;
  gateway_url: string;
  gateway_audience: string;
  subscription_ref?: string | null;
};

function applicationServerKey(value: string): ArrayBuffer {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - value.length % 4) % 4);
  const raw = atob(padded);
  const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function supported(): void {
  if (!window.isSecureContext) throw new Error("push_requires_secure_context");
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    throw new Error("push_not_supported");
  }
}

async function grant(operation: "register" | "delete"): Promise<Grant> {
  return api<Grant>("/api/web-app/notification-subscriptions/grants", {
    method: "POST",
    body: JSON.stringify({ operation }),
  });
}

async function gateway(request: Grant, method: "POST" | "DELETE", body: object): Promise<Record<string, unknown>> {
  const response = await fetch(request.gateway_url, {
    method,
    credentials: "omit",
    redirect: "error",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_version: request.contract_version, grant: request.grant, ...body }),
  });
  const value = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : `push_gateway_failed_${response.status}`);
  return value;
}

async function deleteGatewaySubscription(deviceId: string, subscription: PushSubscription | null): Promise<void> {
  const deletion = await grant("delete");
  await gateway(deletion, "DELETE", { subscription_ref: deletion.subscription_ref });
  await api(`/api/auth/devices/${encodeURIComponent(deviceId)}/notification-subscription`, { method: "DELETE" });
  if (subscription) await subscription.unsubscribe();
}

export async function enableWebPush(deviceId: string): Promise<void> {
  supported();
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error(permission === "denied" ? "notification_permission_denied" : "notification_permission_not_granted");
  const config = await api<PushConfig>("/api/web-app/notification-subscriptions/config");
  if (!config.configured || !config.gateway_url || !config.vapid_public_key) throw new Error("notification_gateway_registration_unavailable");
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  if (existing) {
    try {
      await deleteGatewaySubscription(deviceId, existing);
    } catch (error) {
      if (!(error instanceof Error) || error.message !== "notification_subscription_absent") throw error;
      await existing.unsubscribe();
    }
  }
  const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationServerKey(config.vapid_public_key) });
  try {
    const registrationGrant = await grant("register");
    const result = await gateway(registrationGrant, "POST", { subscription: subscription.toJSON() });
    const subscriptionRef = String(result.subscription_ref || "");
    if (!/^[A-Za-z0-9][A-Za-z0-9._~-]{7,255}$/.test(subscriptionRef)) throw new Error("push_gateway_invalid_subscription_reference");
    await api(`/api/auth/devices/${encodeURIComponent(deviceId)}/notification-subscription`, {
      method: "PUT",
      body: JSON.stringify({ subscription_ref: subscriptionRef, gateway_audience: config.gateway_audience }),
    });
  } catch (error) {
    await subscription.unsubscribe().catch(() => false);
    throw error;
  }
}

export async function disableWebPush(deviceId: string): Promise<void> {
  supported();
  const registration = await navigator.serviceWorker.ready;
  await deleteGatewaySubscription(deviceId, await registration.pushManager.getSubscription());
}
