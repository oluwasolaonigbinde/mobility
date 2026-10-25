import sys
from pathlib import Path

import pytest

from scripts.install_ci_dependencies import runtime_pins, verify_runtime


def test_runtime_parity_checks_all_production_pins_and_pip_consistency(monkeypatch):
    pins = runtime_pins(Path(__file__).resolve().parents[1] / "requirements-production.txt")
    installed = dict(pins)
    monkeypatch.setattr(
        "scripts.install_ci_dependencies.importlib.metadata.version", installed.__getitem__
    )
    calls = []
    monkeypatch.setattr(
        "scripts.install_ci_dependencies.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )
    verify_runtime(pins)
    assert calls == [([sys.executable, "-m", "pip", "check"], {"check": True})]
    installed["fastapi"] = "0.0.0"
    with pytest.raises(RuntimeError, match="Runtime lock mismatch: fastapi"):
        verify_runtime(pins)


@pytest.mark.parametrize("content", ["", "fastapi>=0.115\n", "fastapi==0.115\nfastapi==0.116\n"])
def test_malformed_or_loose_runtime_lock_fails_closed(tmp_path, content):
    lock = tmp_path / "requirements.txt"
    lock.write_text(content)
    with pytest.raises(ValueError):
        runtime_pins(lock)
