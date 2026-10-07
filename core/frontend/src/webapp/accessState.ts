export type AccessPrompt = "loading" | "login" | "passkey";

export function accessPrompt(enrolled: boolean | null): AccessPrompt {
  if (enrolled === null) return "loading";
  return enrolled ? "passkey" : "login";
}
