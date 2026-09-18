"""Tenant context and RBAC (spec 11)."""

from core.tenancy.context import Role, RoleRequiredError, TenantContext, require

__all__ = ["Role", "RoleRequiredError", "TenantContext", "require"]
