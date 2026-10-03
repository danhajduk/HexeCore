import { describe, expect, it } from "vitest";
import { SYSTEM_NAV_ITEMS } from "../layout/Sidebar";
import { PEOPLE_IDENTITY_NOTICE } from "./SettingsPeople";

describe("local People settings", () => {
  it("is separate from login-account settings", () => {
    expect(SYSTEM_NAV_ITEMS).toContainEqual({ label: "People", path: "/settings/people", nested: true });
    expect(SYSTEM_NAV_ITEMS).toContainEqual({ label: "Users", path: "/settings/users", nested: true });
    expect(PEOPLE_IDENTITY_NOTICE).toBe("User ≠ person.");
  });
});
