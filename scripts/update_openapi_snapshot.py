import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rendered = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    (root / "openapi.json").write_text(rendered, encoding="utf-8")
    (root / "docs/api/openapi.snapshot.json").write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
