#!/usr/bin/env python3
"""Update or check the generated current-state inventory in architecture.md."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402

START_MARKER = "<!-- architecture-current-state:start -->"
END_MARKER = "<!-- architecture-current-state:end -->"
LEGACY_START_MARKER = "<!-- BEGIN GENERATED CURRENT-STATE INVENTORY -->"
LEGACY_END_MARKER = "<!-- END GENERATED CURRENT-STATE INVENTORY -->"
HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})
GROUPS = (
    ("/api/v1/admin/*", "/api/v1/admin"),
    ("/api/v1/advertiser/*", "/api/v1/advertiser"),
    ("/api/v1/auth/*", "/api/v1/auth"),
    ("/api/v1/driver/*", "/api/v1/driver"),
    ("/api/v1/health*", "/api/v1/health"),
    ("/api/v1/notifications/*", "/api/v1/notifications"),
    ("/api/v1/webhooks/*", "/api/v1/webhooks"),
)
EXACT_GROUPS = {"/api/v1/me", "/health"}
REQUIRED_ONBOARDING_ROUTES = frozenset(
    {
        "/api/v1/auth/driver-application-status/{reference}",
        "/api/v1/auth/driver-onboarding/files/uploads",
        "/api/v1/auth/driver-onboarding/files/uploads/{upload_id}/confirm",
        "/api/v1/auth/driver-onboarding/files/{file_id}/status",
        "/api/v1/auth/driver-onboarding/person-payee",
        "/api/v1/auth/driver-onboarding/vehicle",
        "/api/v1/auth/register-driver",
    }
)
REQUIRED_DSR_ROUTES = frozenset(
    {
        "/api/v1/admin/privacy/dsr-requests",
        "/api/v1/admin/privacy/dsr-requests/{request_id}/complete",
        "/api/v1/admin/privacy/dsr-requests/{request_id}/inventory",
        "/api/v1/admin/privacy/dsr-requests/{request_id}/locations/{location}",
        "/api/v1/admin/privacy/dsr-requests/{request_id}/verify-identity",
    }
)


class InventoryError(ValueError):
    """Repository state cannot be represented by the approved inventory shape."""


@dataclass(frozen=True)
class RouteGroup:
    prefix: str
    operations: int
    paths: int


@dataclass(frozen=True)
class Inventory:
    operations: int
    paths: int
    api_operations: int
    groups: tuple[RouteGroup, ...]
    tables: int
    revisions: int
    base: str
    head: str


def _route_group(path: str) -> str:
    if path in EXACT_GROUPS:
        return path
    for label, prefix in GROUPS:
        if path.startswith(prefix):
            return label
    raise InventoryError(f"unclassified OpenAPI path: {path}")


def collect_inventory() -> Inventory:
    schema = create_app().openapi()
    grouped_operations: dict[str, int] = defaultdict(int)
    grouped_paths: dict[str, set[str]] = defaultdict(set)
    operation_count = 0

    for path, path_item in schema["paths"].items():
        methods = {method.lower() for method in path_item} & HTTP_METHODS
        if not methods:
            continue
        group = _route_group(path)
        grouped_operations[group] += len(methods)
        grouped_paths[group].add(path)
        operation_count += len(methods)

    paths = set(schema["paths"])
    grouped_path_count = sum(len(grouped_paths[prefix]) for prefix in grouped_paths)
    if grouped_path_count != len(paths):
        counts = f"{grouped_path_count}/{len(paths)}"
        raise InventoryError(f"expected every OpenAPI path to contain an operation: {counts}")
    missing_routes = (REQUIRED_ONBOARDING_ROUTES | REQUIRED_DSR_ROUTES) - paths
    if missing_routes:
        raise InventoryError(f"required current-state routes are missing: {sorted(missing_routes)}")

    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = tuple(scripts.walk_revisions())
    heads = scripts.get_heads()
    bases = scripts.get_bases()
    if len(heads) != 1 or len(bases) != 1:
        detail = f"bases={bases}, heads={heads}"
        raise InventoryError(f"expected one linear Alembic chain, found {detail}")
    if any(revision.is_branch_point or revision.is_merge_point for revision in revisions):
        raise InventoryError("expected a linear Alembic chain without branch or merge points")

    groups = tuple(
        RouteGroup(
            prefix=prefix,
            operations=grouped_operations[prefix],
            paths=len(grouped_paths[prefix]),
        )
        for prefix in sorted(grouped_operations)
    )
    return Inventory(
        operations=operation_count,
        paths=len(paths),
        api_operations=sum(
            grouped_operations[prefix] for prefix in grouped_operations if prefix != "/health"
        ),
        groups=groups,
        tables=len(Base.metadata.tables),
        revisions=len(revisions),
        base=bases[0],
        head=heads[0],
    )


def render_inventory(inventory: Inventory) -> str:
    lines = [
        START_MARKER,
        "<!-- Generated by scripts/update_architecture_inventory.py; do not edit this block. -->",
        "",
        (
            "Current OpenAPI: "
            f"**{inventory.operations} operations across {inventory.paths} paths**; "
            f"**{inventory.api_operations} operations under `/api/v1`** plus root `/health`."
        ),
        "",
        "| Prefix | Operations | Paths |",
        "|--------|-----------:|------:|",
    ]
    lines.extend(
        f"| `{group.prefix}` | {group.operations} | {group.paths} |" for group in inventory.groups
    )
    lines.extend(
        [
            "",
            f"SQLAlchemy metadata contains **{inventory.tables} mapped tables**.",
            (
                f"Alembic contains **{inventory.revisions} linear revisions**, from base "
                f"`{inventory.base}` to the single head `{inventory.head}`."
            ),
            "",
            "Required public driver-onboarding paths:",
            "",
        ]
    )
    lines.extend(f"- `{path}`" for path in sorted(REQUIRED_ONBOARDING_ROUTES))
    lines.extend(["", "Required administrator DSR paths:", ""])
    lines.extend(f"- `{path}`" for path in sorted(REQUIRED_DSR_ROUTES))
    lines.append(END_MARKER)
    return "\n".join(lines)


def render_architecture(text: str, inventory: Inventory) -> str:
    block = render_inventory(inventory)
    if START_MARKER in text or END_MARKER in text:
        if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
            raise InventoryError("architecture current-state markers must occur exactly once")
        marker_pattern = re.compile(
            rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL
        )
        text = marker_pattern.sub(block, text, count=1)
    elif LEGACY_START_MARKER in text or LEGACY_END_MARKER in text:
        if text.count(LEGACY_START_MARKER) != 1 or text.count(LEGACY_END_MARKER) != 1:
            raise InventoryError("legacy architecture inventory markers must occur exactly once")
        marker_pattern = re.compile(
            rf"{re.escape(LEGACY_START_MARKER)}.*?{re.escape(LEGACY_END_MARKER)}",
            re.DOTALL,
        )
        text = marker_pattern.sub(block, text, count=1)
    else:
        legacy_pattern = re.compile(
            r"(### 6\.2 API surface \*\*\[BUILT\]\*\*\n\n).*?(?=The role split )",
            re.DOTALL,
        )
        text, replacements = legacy_pattern.subn(rf"\g<1>{block}\n\n", text, count=1)
        if replacements != 1:
            raise InventoryError("could not locate the architecture API inventory section")

    replacements = (
        (r"(/api/v1 — )\d+( operations)", rf"\g<1>{inventory.api_operations}\g<2>"),
        (
            r"(SQLAlchemy models — )\d+(?: mapped)? tables( \(see §7\))",
            rf"\g<1>{inventory.tables} mapped tables\g<2>",
        ),
        (
            r"(│ )\d+( mapped tables,   │)",
            rf"\g<1>{inventory.tables}\g<2>",
        ),
        (
            r"(### 7\.1 Entities \*\*\[BUILT\]\*\* — )\d+(?: mapped)? tables",
            rf"\g<1>{inventory.tables} mapped tables",
        ),
    )
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise InventoryError(f"architecture owned field did not match exactly once: {pattern}")

    migration_pattern = re.compile(r"- Alembic(?: has)? .*?(?=- `0001` enables)", re.DOTALL)
    migration_text = (
        f"- Alembic has **{inventory.revisions} linear revisions**, from base "
        f"`{inventory.base}` to the single head `{inventory.head}`.\n"
        "  <!-- verified by scripts/update_architecture_inventory.py from Alembic's "
        "ScriptDirectory -->\n"
    )
    text, count = migration_pattern.subn(migration_text, text, count=1)
    if count != 1:
        raise InventoryError("architecture migration inventory did not match exactly once")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update or check architecture.md's generated current-state inventory."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when architecture.md differs from the repository-derived inventory",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    architecture_path = root / "docs" / "architecture.md"
    current = architecture_path.read_text(encoding="utf-8")
    rendered = render_architecture(current, collect_inventory())
    if args.check:
        if rendered != current:
            raise SystemExit(
                "docs/architecture.md current-state inventory is stale; "
                "run scripts/update_architecture_inventory.py"
            )
        return
    architecture_path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
