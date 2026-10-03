import { describe, expect, it } from "vitest";

import { SYSTEM_NAV_ITEMS } from "../layout/Sidebar";
import { USER_ROLES } from "./settings/UserManagementCard";

describe("local user-management navigation", () => {
  it("exposes a nested Users page under Settings", () => {
    expect(SYSTEM_NAV_ITEMS).toContainEqual({ label: "Users", path: "/settings/users", nested: true });
    expect(SYSTEM_NAV_ITEMS).toContainEqual({ label: "People", path: "/settings/people", nested: true });
  });

  it("offers every current Core human role", () => {
    expect(Array.from(USER_ROLES)).toEqual(["owner", "admin", "member", "guest"]);
  });
});
