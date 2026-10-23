import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "app" / "jobs" / "email_delivery.py"
SERVICE_PATH = ROOT / "app" / "services" / "email_delivery.py"


def test_email_service_exposes_only_the_composed_delivery_inputs() -> None:
    tree = ast.parse(SERVICE_PATH.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "process_email_notification"
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
