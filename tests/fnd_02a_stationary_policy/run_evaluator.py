#!/usr/bin/env python3
"""Run the FND-02A decision-evidence evaluator with owner-supplied parameters."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

package_name = __package__ or "fnd_02a_stationary_policy"
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

evaluator_module = importlib.import_module(f"{package_name}.evaluator")
model_module = importlib.import_module(f"{package_name}.model")
evaluate = evaluator_module.evaluate
PolicyChoice = model_module.PolicyChoice
load_fixtures = model_module.load_fixtures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-fixtures", action="store_true")
    parser.add_argument("--option", choices=[choice.value for choice in PolicyChoice])
    parser.add_argument("--params", type=Path)
    parser.add_argument("--fixture", action="append", default=[])
    args = parser.parse_args(argv)

    fixtures = load_fixtures()
    if args.list_fixtures:
        print(json.dumps([fixture.fixture_id for fixture in fixtures], indent=2))
        return 0
    if not args.option or not args.params:
        parser.error("--option and --params are required unless --list-fixtures is used")

    params = json.loads(args.params.read_text(encoding="utf-8"))
    selected = set(args.fixture)
    unknown = selected - {fixture.fixture_id for fixture in fixtures}
    if unknown:
        parser.error("unknown fixture(s): " + ", ".join(sorted(unknown)))

    choice = PolicyChoice(args.option)
    outcomes = [
        asdict(evaluate(fixture, choice, params))
        for fixture in fixtures
        if not selected or fixture.fixture_id in selected
    ]
    print(json.dumps(outcomes, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"FND-02A evaluator refused to run: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
