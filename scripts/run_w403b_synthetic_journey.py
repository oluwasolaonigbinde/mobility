#!/usr/bin/env python3
"""Run the provider-neutral W4-03B synthetic pilot acceptance journey."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__:
    from . import evaluate_pilot_gates
else:
    import evaluate_pilot_gates  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CORRELATION_ID = "w403b-abuja-pilot-001"
STAGES = (
    "advertiser",
    "admin",
    "PWA",
    "synthetic GPS",
    "measurement",
    "Campaign Performance Analysis",
    "qualified synthetic conditional ROI",
    "aggregate contextual activation",
    "payout instruction",
    "incident/recovery",
)
EXPECTED_BLOCKERS = (
    "G-money: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK",
    "G-GPS: BLOCKED — EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, "
    "EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, "
    "EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, DV-PWA-PHYSICAL-MATRIX, "
    "DV-PWA-ROUTE-BATTERY",
    "G-commercial: BLOCKED — EXT-PAYMENT-PROVIDER, EXT-STORAGE-PROVIDER, "
    "EXT-MALWARE-SCANNER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, "
    "EXT-COMMERCIAL-VALUES, EXT-EVIDENCE-POLICY, "
    "EXT-CAMPAIGN-BUDGET-SCOPE, EXT-UPLOAD-POLICY",
    "G-advertiser: BLOCKED — EXT-BASEMAP, EXT-REPORT-METHOD, EXT-LEGAL-PRIVACY",
    "G-moduleG: BLOCKED — EXT-REPORT-METHOD, EXT-LEGAL-PRIVACY, EXT-AD-PLATFORM",
    "G-pilot: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, "
    "EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, "
    "EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, "
    "EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, "
    "EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, "
    "EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, "
    "EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, DV-PWA-PHYSICAL-MATRIX, "
    "DV-PWA-ROUTE-BATTERY, DV-STAGING-LIVE",
)


class JourneyError(RuntimeError):
    """The synthetic journey contradicted its frozen acceptance contract."""


def run_build_path(
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-s",
        "tests/test_w403b_synthetic_path.py::test_correlated_synthetic_pilot_journey",
    )
    result = runner(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise JourneyError("synthetic build path failed")


def evaluate_live_boundaries(
    environment: Mapping[str, str],
    evaluator: Callable[..., int] = evaluate_pilot_gates.main,
) -> tuple[str, ...]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = evaluator(environment=dict(environment))
    lines = tuple(stdout.getvalue().splitlines())
    if exit_code != 1 or lines != EXPECTED_BLOCKERS or stderr.getvalue() != "":
        raise JourneyError(
            "live-boundary evaluation must return exit 1, exact ordered blockers, and empty stderr"
        )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("usage: run_w403b_synthetic_journey.py", file=sys.stderr)
        return 2
    try:
        run_build_path()
        blockers = evaluate_live_boundaries(os.environ)
    except JourneyError as exc:
        print(f"W4-03B synthetic journey failed: {exc}", file=sys.stderr)
        return 1
    for line in blockers:
        print(line)
    print(f"W4-03B synthetic journey PASS — {CORRELATION_ID}; all live boundaries remain blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
