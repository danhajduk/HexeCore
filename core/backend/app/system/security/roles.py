from __future__ import annotations

from enum import Enum


class AuthRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    service = "service"
    guest = "guest"


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    AuthRole.owner.value: frozenset({"core.admin", "users.manage", "people.manage", "people.self", "ownership.manage", "sessions.manage", "sessions.self"}),
    AuthRole.admin.value: frozenset({"core.admin", "users.manage", "people.manage", "people.self", "sessions.manage", "sessions.self"}),
    AuthRole.member.value: frozenset({"people.self", "sessions.self"}),
    AuthRole.guest.value: frozenset({"people.self", "sessions.self"}),
}


def role_has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(str(role or "").strip().lower(), frozenset())
