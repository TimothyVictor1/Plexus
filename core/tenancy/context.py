"""Tenant context and RBAC roles (spec 11).

Every request, Temporal activity, and span carries a TenantContext. Roles are ordered: a higher
role includes every lower one.
"""

from __future__ import annotations

import re
from enum import IntEnum

from pydantic import BaseModel, Field, field_validator

TENANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
SANDBOX_PREFIX = "sandbox-"


class Role(IntEnum):
    viewer = 1
    operator = 2
    approver = 3
    admin = 4

    @classmethod
    def parse(cls, name: str) -> Role:
        try:
            return cls[name]
        except KeyError as exc:
            msg = f"unknown role: {name!r}"
            raise ValueError(msg) from exc

    def includes(self, other: Role) -> bool:
        return self >= other


class TenantContext(BaseModel):
    tenant_id: str
    subject: str = Field(description="Authenticated principal id (OIDC sub) or system actor")
    roles: frozenset[Role] = Field(default_factory=frozenset)
    trace_id: str = Field(min_length=1)

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant_id(cls, value: str) -> str:
        if not TENANT_ID_PATTERN.match(value):
            msg = f"invalid tenant_id {value!r}; expected {TENANT_ID_PATTERN.pattern}"
            raise ValueError(msg)
        return value

    @property
    def highest_role(self) -> Role | None:
        return max(self.roles) if self.roles else None

    def has(self, role: Role) -> bool:
        highest = self.highest_role
        return highest is not None and highest.includes(role)

    @property
    def is_sandbox(self) -> bool:
        """Sandbox tenants exist only for the immune system (spec 07)."""
        return self.tenant_id.startswith(SANDBOX_PREFIX)


class RoleRequiredError(PermissionError):
    def __init__(self, required: Role, ctx: TenantContext) -> None:
        self.required = required
        self.ctx = ctx
        super().__init__(f"role {required.name} required; principal has {ctx.highest_role}")


def require(ctx: TenantContext, role: Role) -> None:
    """Raise RoleRequiredError unless ctx holds `role` or higher."""
    if not ctx.has(role):
        raise RoleRequiredError(role, ctx)
