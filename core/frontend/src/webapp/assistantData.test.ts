import { describe, expect, it } from "vitest";
import { normalizeBootstrap, normalizeConversations, normalizeMessages } from "./assistantData";

describe("assistant response normalization", () => {
  it("provides safe defaults for partial bootstrap responses", () => {
    expect(normalizeBootstrap({ user: { permissions: null } })).toEqual({ core: { core_name: "Assistant" }, user: { username: "", role: "", permissions: [] } });
  });
  it("ignores malformed conversations and messages", () => {
    expect(normalizeConversations([null, {}, { conversation_id: "conv-1", title: null }])).toEqual([{ conversation_id: "conv-1", title: "Conversation", updated_at: "" }]);
    expect(normalizeMessages([null, {}, { message_id: "msg-1", role: "user", content: null }])).toEqual([{ message_id: "msg-1", role: "user", content: "", created_at: "" }]);
  });
});
