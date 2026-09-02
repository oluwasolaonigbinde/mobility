"""Generated authorization inventory for every externally addressable API route."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import Any

from fastapi.routing import APIRoute
from pydantic import TypeAdapter

from app.main import create_app


class Principal(StrEnum):
    ADMIN = "admin"
    ADVERTISER = "advertiser"
    DRIVER = "driver"
    AUTHENTICATED = "authenticated"
    APPLICANT = "applicant_capability"
    MACHINE = "machine_callback"
    PUBLIC = "public"


class Action(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    TRANSITION = "transition"
    DOWNLOAD = "download"
    EXPORT = "export"
    JOB = "job"
    CALLBACK = "callback"


@dataclass(frozen=True, slots=True)
class GovernedRoute:
    method: str
    path: str
    principal: Principal
    action: Action
    tenant_scope: str
    resource: str
    dependency_names: frozenset[str]

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.path


PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/health/ready"),
        ("GET", "/api/v1/health/partitions"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/password-reset/request"),
        ("POST", "/api/v1/auth/password-reset/complete"),
        ("POST", "/api/v1/auth/register-driver"),
        ("GET", "/api/v1/auth/driver-application-status/{reference}"),
    }
)

APPLICANT_ROUTES = frozenset(
    {
        ("POST", "/api/v1/auth/driver-onboarding/files/uploads"),
        ("POST", "/api/v1/auth/driver-onboarding/files/uploads/{upload_id}/confirm"),
        ("POST", "/api/v1/auth/driver-onboarding/files/{file_id}/status"),
        ("POST", "/api/v1/auth/driver-onboarding/person-payee"),
        ("POST", "/api/v1/auth/driver-onboarding/vehicle"),
    }
)

MACHINE_ROUTES = frozenset(
    {
        ("POST", "/api/v1/webhooks/payments"),
        ("POST", "/api/v1/notifications/email/delivery-receipts"),
        ("POST", "/api/v1/admin/payout-batches/provider-webhook"),
    }
)

_TRANSITION_TERMS = frozenset(
    {
        "accept",
        "acknowledge",
        "activate",
        "allocate",
        "approve",
        "cancel",
        "complete",
        "confirm",
        "deactivate",
        "decline",
        "discard",
        "end",
        "execute",
        "issue",
        "poll",
        "read",
        "read-all",
        "reconcile",
        "reject",
        "resolve",
        "reserve",
        "resume",
        "retry-failed",
        "reverse",
        "rewrap",
        "start",
        "submit",
        "verify",
        "void",
        "withdraw",
    }
)


def _routes(app_routes: Iterable[object], prefix: str = "") -> Iterable[tuple[APIRoute, str]]:
    for route in app_routes:
        if isinstance(route, APIRoute):
            yield route, f"{prefix}{route.path}"
            continue
        original_router = getattr(route, "original_router", None)
        include_context = getattr(route, "include_context", None)
        if original_router is not None and include_context is not None:
            yield from _routes(original_router.routes, f"{prefix}{include_context.prefix}")


def _dependency_names(route: APIRoute) -> frozenset[str]:
    return frozenset(
        getattr(dependency.call, "__name__", dependency.call.__class__.__name__)
        for dependency in route.dependant.dependencies
    )


def _principal(key: tuple[str, str], dependencies: frozenset[str]) -> Principal:
    if key in PUBLIC_ROUTES:
        return Principal.PUBLIC
    if key in APPLICANT_ROUTES:
        return Principal.APPLICANT
    if key in MACHINE_ROUTES:
        return Principal.MACHINE
    by_dependency = {
        "require_admin_user": Principal.ADMIN,
        "require_advertiser_user": Principal.ADVERTISER,
        "require_driver_user": Principal.DRIVER,
        "get_current_user": Principal.AUTHENTICATED,
    }
    matched = {principal for name, principal in by_dependency.items() if name in dependencies}
    if len(matched) != 1:
        raise AssertionError(
            f"Route {key!r} has no single classified authorization principal: "
            f"{sorted(dependencies)}"
        )
    return matched.pop()


def _action(method: str, path: str, principal: Principal) -> Action:
    if principal is Principal.MACHINE:
        return Action.CALLBACK
    final = path.rstrip("/").rsplit("/", 1)[-1]
    if final == "download":
        return Action.DOWNLOAD
    if "export" in final:
        return Action.EXPORT
    if any(term in path for term in ("recompute", "estimate", "evaluation")):
        return Action.JOB
    if final in _TRANSITION_TERMS:
        return Action.TRANSITION
    return {
        "GET": Action.READ,
        "POST": Action.CREATE,
        "PUT": Action.UPDATE,
        "PATCH": Action.UPDATE,
        "DELETE": Action.DELETE,
    }[method]


def _resource(path: str) -> str:
    parts = [part for part in path.split("/") if part and part not in {"api", "v1"}]
    for index, part in enumerate(parts):
        if part.startswith("{") and index:
            return parts[index - 1]
    return parts[-1] if parts else "root"


def authorization_inventory() -> tuple[GovernedRoute, ...]:
    inventory: list[GovernedRoute] = []
    for route, path in _routes(create_app().routes):
        if path.startswith(("/docs", "/redoc", "/openapi")):
            continue
        dependencies = _dependency_names(route)
        for method in sorted(route.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
            key = method, path
            principal = _principal(key, dependencies)
            tenant_scope = {
                Principal.ADVERTISER: "advertiser_organization",
                Principal.DRIVER: "driver_owner",
                Principal.APPLICANT: "driver_application",
                Principal.MACHINE: "signed_provider",
                Principal.ADMIN: "platform_admin",
                Principal.AUTHENTICATED: "current_actor",
                Principal.PUBLIC: "public",
            }[principal]
            inventory.append(
                GovernedRoute(
                    method=method,
                    path=path,
                    principal=principal,
                    action=_action(method, path, principal),
                    tenant_scope=tenant_scope,
                    resource=_resource(path),
                    dependency_names=dependencies,
                )
            )
    return tuple(sorted(inventory, key=lambda item: item.key))


def concrete_path(path: str, *, opaque_id: str) -> str:
    values = {
        "artifact_format": "csv",
        "location": "database",
        "reference": "missing-reference",
    }
    for component in path.split("/"):
        if component.startswith("{") and component.endswith("}"):
            name = component[1:-1]
            path = path.replace(component, values.get(name, opaque_id))
    return path


def _schema_value(schema: dict[str, Any], root: dict[str, Any], *, field_name: str = "") -> Any:
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _schema_value(target, root, field_name=field_name)
    for union_key in ("anyOf", "oneOf"):
        if union_key in schema:
            choice = next(
                (item for item in schema[union_key] if item.get("type") != "null"),
                schema[union_key][0],
            )
            return _schema_value(choice, root, field_name=field_name)
    named_values = {
        "account_name": "Matrix Applicant",
        "account_number": "0123456789",
        "bank_code": "999",
        "code": "123456",
        "content_type": "image/png",
        "currency": "NGN",
        "decision": "rejected",
        "email": "matrix@example.com",
        "filename": "matrix.png",
        "nin": "12345678901",
        "phone_number": "+2348012345678",
        "plate_country_code": "NG",
        "plate_number": "ABC-123",
        "reason": "Authorization matrix denial",
        "reason_code": "missing_evidence",
        "sha256": "0" * 64,
        "verification_reference": "matrix-verification-reference-0001",
    }
    if field_name in named_values:
        return named_values[field_name]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "default" in schema and schema["default"] is not None:
        return schema["default"]

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        return {
            name: _schema_value(properties[name], root, field_name=name)
            for name in schema.get("required", ())
        }
    if schema_type == "array":
        size = max(1, schema.get("minItems", 0))
        return [
            _schema_value(schema.get("items", {}), root, field_name=field_name) for _ in range(size)
        ]
    if schema_type in {"integer", "number"}:
        return max(schema.get("minimum", schema.get("exclusiveMinimum", 0)) + 1, 1)
    if schema_type == "boolean":
        return True
    if schema_type == "string" or schema.get("format"):
        formatted = {
            "date": "2026-09-02",
            "date-time": "2026-09-02T12:00:00Z",
            "email": "matrix@example.com",
            "uri": "https://example.com/matrix",
            "uuid": "ffffffff-ffff-4fff-8fff-ffffffffffff",
        }
        value = formatted.get(schema.get("format"), "matrix")
        minimum = schema.get("minLength", 0)
        return value.ljust(minimum, "x")
    return {}


@cache
def request_payload(route: GovernedRoute) -> Any:
    api_route = next(
        candidate
        for candidate, path in _routes(create_app().routes)
        if path == route.path and route.method in candidate.methods
    )
    if api_route.body_field is None:
        return {}
    annotation = api_route.body_field.field_info.annotation
    schema = TypeAdapter(annotation).json_schema()
    payload = _schema_value(schema, schema)
    if route.path.endswith("/campaign-assignments/{assignment_id}/files/uploads"):
        payload["purpose"] = "installation_evidence"
    if route.path.endswith("/exposure-segments/{segment_id}/delivery-approvals"):
        payload["provider"] = "controlled-csv-v1"
    if route.path.endswith("/files/{file_id}/download") and route.principal is Principal.ADMIN:
        payload["purpose"] = "creative_review"
    if route.path.endswith("/quotations/{revision_id}/accept-external"):
        payload.update(
            {
                "acceptance_method": "external_recorded",
                "external_accepted_at": "2026-09-02T12:00:00Z",
                "external_acceptance_reference": "matrix-external-acceptance",
            }
        )
    if route.path.endswith("/campaigns/{campaign_id}/change-requests"):
        payload["budget_amount"] = "1.00"
    return payload
