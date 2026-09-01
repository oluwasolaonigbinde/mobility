import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "app" / "jobs" / "email_delivery.py"
SERVICE_PATH = ROOT / "app" / "services" / "email_delivery.py"


def _imported_names(tree: ast.AST) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.setdefault(alias.name, set())
    return imports


def test_email_job_is_selection_and_composition_only() -> None:
    tree = ast.parse(JOB_PATH.read_text())
    imports = _imported_names(tree)

    assert SERVICE_PATH.exists()
    assert set(imports) <= {
        "datetime",
        "typing",
        "sqlalchemy",
        "sqlalchemy.ext.asyncio",
        "app.adapters.messaging",
        "app.core.config",
        "app.models.notification",
        "app.services.email_delivery",
    }
    assert imports["sqlalchemy"] <= {"or_", "select"}
    assert imports["app.adapters.messaging"] <= {"EmailAdapter", "build_email_adapter"}
    assert imports["app.core.config"] <= {"Settings", "get_settings"}
    assert imports["app.models.notification"] <= {
        "Notification",
        "NotificationChannel",
        "NotificationStatus",
    }
    assert imports["app.services.email_delivery"] == {"process_email_notification"}

    functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)]
    assert [function.name for function in functions] == ["sweep_email_notifications"]

    forbidden_fields = {
        "attempt_count",
        "delivery_claim_token",
        "delivery_claim_expires_at",
        "last_error_code",
        "next_attempt_at",
        "provider_message_id",
        "sent_at",
        "status",
    }
    written_fields: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        elif isinstance(node, ast.AugAssign):
            targets.append(node.target)
        for target in targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Attribute):
                    written_fields.add(child.attr)
    assert written_fields.isdisjoint(forbidden_fields)


def test_email_service_exposes_only_the_composed_delivery_inputs() -> None:
    tree = ast.parse(SERVICE_PATH.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "process_email_notification"
    )

    assert [argument.arg for argument in function.args.args] == ["sessionmaker"]
    assert [argument.arg for argument in function.args.kwonlyargs] == [
        "notification_id",
        "settings",
        "email_adapter",
        "now",
    ]
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "get_settings" not in imported_names
    assert "build_email_adapter" not in imported_names
