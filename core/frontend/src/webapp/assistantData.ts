export type AssistantBootstrap = { core: { core_name: string }; user: { username: string; role: string; permissions: string[] } };
export type AssistantConversation = { conversation_id: string; title: string; updated_at: string };
export type AssistantMessage = { message_id: string; role: "user" | "assistant"; content: string; created_at: string };
export type AssistantNotification = { intent_id: number; event_id: string; category: string; severity: string; title: string; body: string; navigation_path: string; created_at: string; status: string };

export function normalizeBootstrap(value: unknown): AssistantBootstrap {
  const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const core = payload.core && typeof payload.core === "object" ? payload.core as Record<string, unknown> : {};
  const user = payload.user && typeof payload.user === "object" ? payload.user as Record<string, unknown> : {};
  return {
    core: { core_name: typeof core.core_name === "string" && core.core_name ? core.core_name : "Assistant" },
    user: { username: typeof user.username === "string" ? user.username : "", role: typeof user.role === "string" ? user.role : "", permissions: Array.isArray(user.permissions) ? user.permissions.filter((item): item is string => typeof item === "string") : [] },
  };
}

export function normalizeConversations(value: unknown): AssistantConversation[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (typeof row.conversation_id !== "string" || !row.conversation_id) return [];
    return [{ conversation_id: row.conversation_id, title: typeof row.title === "string" && row.title ? row.title : "Conversation", updated_at: typeof row.updated_at === "string" ? row.updated_at : "" }];
  });
}

export function normalizeMessages(value: unknown): AssistantMessage[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (typeof row.message_id !== "string" || !row.message_id) return [];
    return [{ message_id: row.message_id, role: row.role === "user" ? "user" : "assistant", content: typeof row.content === "string" ? row.content : "", created_at: typeof row.created_at === "string" ? row.created_at : "" }];
  });
}

export function normalizeNotifications(value: unknown): AssistantNotification[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (typeof row.intent_id !== "number" || typeof row.event_id !== "string" || !row.event_id) return [];
    return [{ intent_id: row.intent_id, event_id: row.event_id, category: typeof row.category === "string" ? row.category : "update", severity: typeof row.severity === "string" ? row.severity : "info", title: typeof row.title === "string" && row.title ? row.title : "Hexe update", body: typeof row.body === "string" ? row.body : "", navigation_path: typeof row.navigation_path === "string" && row.navigation_path.startsWith("/app") ? row.navigation_path : "/app", created_at: typeof row.created_at === "string" ? row.created_at : "", status: typeof row.status === "string" ? row.status : "pending" }];
  });
}
