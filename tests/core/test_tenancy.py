from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.tenancy import Role, RoleRequiredError, TenantContext, require


def ctx(*roles: Role, tenant: str = "acme") -> TenantContext:
    return TenantContext(tenant_id=tenant, subject="u1", roles=frozenset(roles), trace_id="t")


def test_roles_are_ordered() -> None:
    assert Role.viewer < Role.operator < Role.approver < Role.admin


@pytest.mark.parametrize(
    ("held", "needed", "ok"),
    [
        (Role.admin, Role.approver, True),
        (Role.approver, Role.approver, True),
        (Role.operator, Role.approver, False),
        (Role.viewer, Role.operator, False),
    ],
)
def test_require(held: Role, needed: Role, ok: bool) -> None:
    c = ctx(held)
    if ok:
        require(c, needed)
    else:
        with pytest.raises(RoleRequiredError):
            require(c, needed)


def test_no_roles_denied() -> None:
    with pytest.raises(RoleRequiredError):
        require(ctx(), Role.viewer)


@pytest.mark.parametrize("bad", ["", "A", "-x", "x" * 64, "tenant id", "Tcl"])
def test_invalid_tenant_ids_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        TenantContext(tenant_id=bad, subject="s", trace_id="t")


@given(st.from_regex(r"^[a-z0-9][a-z0-9-]{1,62}$", fullmatch=True))
def test_valid_tenant_ids_accepted(tenant: str) -> None:
    assert TenantContext(tenant_id=tenant, subject="s", trace_id="t").tenant_id == tenant


def test_sandbox_detection() -> None:
    assert ctx(tenant="sandbox-acme").is_sandbox
    assert not ctx(tenant="acme").is_sandbox


def test_role_parse() -> None:
    assert Role.parse("approver") is Role.approver
    with pytest.raises(ValueError, match="unknown role"):
        Role.parse("root")
