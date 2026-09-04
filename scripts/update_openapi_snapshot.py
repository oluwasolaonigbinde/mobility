import argparse
import json
from pathlib import Path

from app.main import create_app

ARTIFACT_RELATIVE_PATHS = (
    Path("openapi.json"),
    Path("docs/api/openapi.snapshot.json"),
)


def render_openapi() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def _artifact_paths(root: Path) -> tuple[Path, ...]:
    return tuple(root / relative_path for relative_path in ARTIFACT_RELATIVE_PATHS)


def _stale_artifacts(root: Path, rendered: str) -> tuple[Path, ...]:
    return tuple(
        path
        for path in _artifact_paths(root)
        if not path.is_file() or path.read_text(encoding="utf-8") != rendered
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update or check the OpenAPI JSON artifacts.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when either committed JSON artifact differs from FastAPI output",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    rendered = render_openapi()
    stale_artifacts = _stale_artifacts(root, rendered)
    if args.check:
        if stale_artifacts:
            names = ", ".join(str(path.relative_to(root)) for path in stale_artifacts)
            raise SystemExit(f"OpenAPI artifacts are stale: {names}")
        return

    for path in _artifact_paths(root):
        path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
