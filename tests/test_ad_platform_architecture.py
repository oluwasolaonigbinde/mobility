import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "app" / "services" / "audience_delivery.py"
DEPENDENCIES_PATH = ROOT / "app" / "api" / "v1" / "dependencies.py"
ADAPTER_PACKAGE_PATH = ROOT / "app" / "adapters" / "ad_platforms" / "__init__.py"


def _imports(tree: ast.AST) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.setdefault(alias.name, set())
    return imports


def test_ad_platform_port_and_composition_respect_adapter_boundary() -> None:
    service_tree = ast.parse(SERVICE_PATH.read_text())
    dependencies_tree = ast.parse(DEPENDENCIES_PATH.read_text())
    service_imports = _imports(service_tree)
    dependency_imports = _imports(dependencies_tree)

    assert ADAPTER_PACKAGE_PATH.exists()
    assert service_imports["app.adapters.ad_platforms"] == {
        "AdPlatformActivationRequest",
        "AdPlatformAdapter",
    }
    assert not {
        "DisabledAdPlatformAdapter",
        "FakeAdPlatformAdapter",
        "build_ad_platform_adapter",
    } & {
        node.name
        for node in service_tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert dependency_imports["app.adapters.ad_platforms"] == {
        "AdPlatformAdapter",
        "build_ad_platform_adapter",
    }
    assert "app.adapters.ad_platforms.provider" not in dependency_imports
    assert not {
        "AdPlatformAdapter",
        "DisabledAdPlatformAdapter",
        "FakeAdPlatformAdapter",
        "build_ad_platform_adapter",
    } & dependency_imports.get("app.services.audience_delivery", set())
