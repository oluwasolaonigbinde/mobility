from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.db.base import Base
from app.models.user import User, UserRole, UserStatus
from tests.conftest import create_test_user

SERVICE_ROOT = Path(__file__).parents[1] / "app" / "services"

MIGRATED_CALL_SITES: dict[str, tuple[str, ...]] = {
    "billing": (
        "request_custom_quote",
        "record_quotation_revision",
        "accept_quotation_revision",
        "record_payment_receipt",
        "reconcile_payment_receipt",
        "confirm_payment_receipt",
        "allocate_payment_receipt",
        "reverse_payment_receipt",
        "record_invoice_issuer_profile",
        "create_invoice_draft",
        "issue_invoice",
        "_append_financial_authorization",
        "record_approved_credit_authorization",
        "reserve_assignment_liability",
        "record_production_start",
        "record_invoice_correction",
        "record_refund_settlement",
        "record_credit_contract_settlement",
    ),
    "campaign_assignments": (
        "create_campaign_assignment",
        "activate_admin_assignment",
        "cancel_admin_assignment",
    ),
    "campaign_changes": ("decide_campaign_change",),
    "heatmaps": ("admin_heatmap",),
    "audience": (
        "list_admin_retargeting_sources",
        "get_admin_retargeting_source",
        "_link_access",
        "list_retargeting_source_links",
        "high_exposure_zone_insights",
    ),
    "audience_delivery": ("_segment_access",),
    "measurement": ("issue_measurement_run",),
    "disbursements": (
        "create_payout_batch_draft",
        "reserve_payout_batch",
        "approve_payout_batch",
        "submit_payout_batch",
        "_apply_verified_line_evidence",
        "poll_payout_line",
        "retry_failed_payout_lines",
        "void_payout_batch",
    ),
    "payees": (
        "create_pilot_payee",
        "add_verified_bank_account_version",
        "verify_bank_account_version_for_payout",
        "read_verified_bank_account",
        "rewrap_bank_account",
    ),
    "driver_applications": ("list_driver_applications",),
}


def _service_tree(service_name: str) -> ast.Module:
    return ast.parse((SERVICE_ROOT / f"{service_name}.py").read_text())


def _named_functions(tree: ast.Module) -> dict[str, ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    }


def _canonical_calls(function: ast.AsyncFunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "require_active_admin"
    ]


def test_all_44_sites_import_and_call_only_the_canonical_authority() -> None:
    assert sum(map(len, MIGRATED_CALL_SITES.values())) == 44
    for service_name, expected_functions in MIGRATED_CALL_SITES.items():
        tree = _service_tree(service_name)
        functions = _named_functions(tree)
        imports = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "app.services.admin_authorization"
        ]
        assert len(imports) == 1
        assert [alias.name for alias in imports[0].names] == ["require_active_admin"]
        assert all(len(_canonical_calls(functions[name])) == 1 for name in expected_functions)
        assert not ({"_active_admin", "_require_active_admin"} & functions.keys())

    for service_name in ("campaign_assignments", "campaign_changes", "audience_delivery"):
        assert not any(
            isinstance(node, ast.ImportFrom)
            and any(
                alias.name in {"_active_admin", "_require_active_admin"}
                for alias in node.names
            )
            for node in _service_tree(service_name).body
        )


def _first_call_line(function: ast.AsyncFunctionDef, names: set[str]) -> int:
    return min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id in names
            or isinstance(node.func, ast.Attribute)
            and node.func.attr in names
        )
    )


def test_named_admin_branches_authorize_before_protected_domain_access() -> None:
    functions = _named_functions(_service_tree("billing"))
    assert _first_call_line(
        functions["request_custom_quote"], {"require_active_admin"}
    ) < _first_call_line(functions["request_custom_quote"], {"_campaign"})
    assert _first_call_line(
        functions["accept_quotation_revision"], {"require_active_admin"}
    ) < _first_call_line(
        functions["accept_quotation_revision"], {"get", "acquire_campaign_terms_lock"}
    )
    assert _first_call_line(
        functions["record_approved_credit_authorization"], {"require_active_admin"}
    ) < _first_call_line(
        functions["record_approved_credit_authorization"],
        {"_commercial_terms_for_campaign"},
    )

    credit_function = functions["record_approved_credit_authorization"]
    lock_loop = next(node for node in credit_function.body if isinstance(node, ast.For))
    assert isinstance(lock_loop.iter, ast.Call)
    assert isinstance(lock_loop.iter.func, ast.Name)
    assert lock_loop.iter.func.id == "sorted"
    assert isinstance(lock_loop.iter.args[0], ast.Set)
    assert {
        element.id
        for element in lock_loop.iter.args[0].elts
        if isinstance(element, ast.Name)
    } == {"actor_user_id", "approved_by_user_id"}


def test_canonical_authority_owns_the_locked_forbidden_role_envelope() -> None:
    tree = _service_tree("admin_authorization")
    function = _named_functions(tree)["require_active_admin"]
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "with_for_update"
        for node in ast.walk(function)
    )
    source = (SERVICE_ROOT / "admin_authorization.py").read_text()
    assert '"FORBIDDEN_ROLE"' in source
    assert '"Admin role is required"' in source
    assert "HTTP_403_FORBIDDEN" in source


def _module(service_name: str) -> ModuleType:
    return importlib.import_module(f"app.services.{service_name}")


def _required_argument(
    function: Callable,
    name: str,
    *,
    denied_user_id: UUID,
    active_admin_id: UUID,
    settings,
):
    if name == "session":
        raise AssertionError("session is supplied separately")
    if name in {"actor_user_id", "admin_user_id", "user_id"}:
        return denied_user_id
    if name == "approved_by_user_id":
        return active_admin_id
    if name == "settings":
        return settings
    if name == "source":
        return "poll" if function.__name__ == "_apply_verified_line_evidence" else object()
    if name in {"admin", "require_admin"}:
        return True
    if name.endswith("_id"):
        return uuid4()
    if name.endswith("_ids"):
        return (uuid4(),)
    if name in {"due_at", "occurred_at", "external_accepted_at"}:
        return datetime.now(UTC) + timedelta(days=1)
    if name in {"limit", "offset"}:
        return 1
    return object()


async def _invoke_denied_site(
    session,
    service_name: str,
    function_name: str,
    *,
    denied_user_id: UUID,
    active_admin_id: UUID,
    settings,
) -> None:
    function = getattr(_module(service_name), function_name)
    kwargs = {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.name == "session":
            continue
        if parameter.default is not inspect.Parameter.empty and parameter.name not in {
            "admin",
            "require_admin",
        }:
            continue
        kwargs[parameter.name] = _required_argument(
            function,
            parameter.name,
            denied_user_id=denied_user_id,
            active_admin_id=active_admin_id,
            settings=settings,
        )
    with pytest.raises(AppError) as caught:
        await function(session, **kwargs)
    assert (
        caught.value.code,
        caught.value.message,
        caught.value.status_code,
    ) == ("FORBIDDEN_ROLE", "Admin role is required", 403)


async def _table_counts(session) -> dict[str, int]:
    return {
        table.name: int(await session.scalar(select(func.count()).select_from(table)) or 0)
        for table in Base.metadata.sorted_tables
    }


def test_each_migrated_entry_point_denies_without_mutation(
    db_sessionmaker, settings
) -> None:
    async def scenario() -> None:
        active_admin = User(
            id=UUID(int=10),
            email="r08-active-admin@example.com",
            password_hash="unused",
            full_name="Active Admin",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        denied_users = (
            User(
                id=UUID(int=20),
                email="r08-disabled@example.com",
                password_hash="unused",
                full_name="Disabled Admin",
                role=UserRole.ADMIN,
                status=UserStatus.DISABLED,
            ),
            User(
                id=UUID(int=30),
                email="r08-suspended@example.com",
                password_hash="unused",
                full_name="Suspended Admin",
                role=UserRole.ADMIN,
                status=UserStatus.SUSPENDED,
            ),
            User(
                id=UUID(int=40),
                email="r08-advertiser@example.com",
                password_hash="unused",
                full_name="Active Advertiser",
                role=UserRole.ADVERTISER,
                status=UserStatus.ACTIVE,
            ),
        )
        async with db_sessionmaker() as session:
            session.add_all((active_admin, *denied_users))
            await session.commit()
            before = await _table_counts(session)
            denied_ids = tuple(user.id for user in denied_users) + (UUID(int=50),)
            for denied_user_id in denied_ids:
                for service_name, function_names in MIGRATED_CALL_SITES.items():
                    for function_name in function_names:
                        await _invoke_denied_site(
                            session,
                            service_name,
                            function_name,
                            denied_user_id=denied_user_id,
                            active_admin_id=active_admin.id,
                            settings=settings,
                        )

                await _invoke_denied_site(
                    session,
                    "billing",
                    "record_approved_credit_authorization",
                    denied_user_id=active_admin.id,
                    active_admin_id=denied_user_id,
                    settings=settings,
                )
            assert await _table_counts(session) == before
            assert not session.new
            assert not session.deleted

    asyncio.run(scenario())


def test_http_dependency_keeps_user_not_active_for_a_disabled_token(
    db_client, db_sessionmaker
) -> None:
    password = "long-secure-password"
    admin = create_test_user(
        db_sessionmaker,
        email="r08-disabled-token@example.com",
        password=password,
    )
    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": password},
    )
    assert login.status_code == 200

    async def disable() -> None:
        async with db_sessionmaker() as session:
            persisted = await session.get(User, admin.id)
            assert persisted is not None
            persisted.status = UserStatus.DISABLED
            await session.commit()

    asyncio.run(disable())
    response = db_client.get(
        "/api/v1/admin/driver-applications",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_NOT_ACTIVE"
