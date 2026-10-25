"""Install the production lock, then tooling constrained by that exact runtime."""

import argparse
import importlib.metadata
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;\\]+)\s*(?:\\)?$")


def runtime_pins(lock: Path) -> dict[str, str]:
    pins = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError("Production lock must contain only exact package pins and hashes")
        name, version = match.groups()
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in pins:
            raise ValueError(f"Duplicate production pin: {normalized}")
        pins[normalized] = version
    if not pins:
        raise ValueError("Production lock is empty")
    return pins


def verify_runtime(pins: dict[str, str]) -> None:
    for name, expected in pins.items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError(
                f"Runtime lock mismatch: {name}: installed {actual}, locked {expected}"
            )
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    print(f"Production runtime parity: {len(pins)} exact installed versions; pip check passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--check", action="store_true", help="Verify without installing")
    args = parser.parse_args()
    lock = ROOT / "requirements-production.txt"
    pins = runtime_pins(lock)
    if not args.check:
        pip = [sys.executable, "-m", "pip", "install"]
        subprocess.run([*pip, "--require-hashes", "-r", str(lock)], check=True)
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        groups = ["dev", "static"] if args.static else ["dev"]
        tooling = [
            item for group in groups for item in project["project"]["optional-dependencies"][group]
        ]
        with tempfile.TemporaryDirectory(prefix="cardvert-runtime-constraints-") as temporary:
            constraints = Path(temporary) / "runtime.txt"
            constraints.write_text(
                "".join(f"{name}=={version}\n" for name, version in pins.items()), encoding="utf-8"
            )
            subprocess.run([*pip, "--constraint", str(constraints), *tooling], check=True)
        # Editable metadata is useful for tooling; extras must never resolve runtime again.
        subprocess.run([*pip, "--no-deps", "-e", str(ROOT)], check=True)
    verify_runtime(pins)


if __name__ == "__main__":
    main()
