export type AccessPrompt = "loading" | "login" | "passkey";
export type AssistantEntry = "checking" | "locked" | "authenticated";

export function accessPrompt(enrolled: boolean | null): AccessPrompt {
  if (enrolled === null) return "loading";
  return enrolled ? "passkey" : "login";
}

export function assistantEntry(enrolled: boolean, hasAccessToken: boolean, unlocked: boolean): AssistantEntry {
  if (!hasAccessToken) return "locked";
  if (enrolled && !unlocked) return "locked";
  return "authenticated";
}

export function backgroundSessionExpired(backgroundedAt: number, now: number, timeoutMs = 5 * 60 * 1000): boolean {
  return backgroundedAt > 0 && now - backgroundedAt >= timeoutMs;
}
