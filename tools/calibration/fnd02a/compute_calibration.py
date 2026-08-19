#!/usr/bin/env python3
"""FND-02A Option-A calibration computation (P1/P2 -> P3 acceptance).

Ingests capture CSVs (see CAPTURE-FORMAT.md), computes sliding-window net
displacement distributions per corpus and window size, and evaluates the P3
acceptance rule:

    jitter_p95(window) * 1.2 <= threshold <= creep_p05(window) * 0.8

for every candidate (window, threshold) pair in the reviewed conservative
ranges (windows {90,120,145} s, thresholds 20..40 m). Fails closed: if no
pair satisfies the rule, it prints the measured distributions and exits 3 so
the owner escalation path (Option B/C re-selection) triggers instead of a
forced value.

Also reports the fix-poor rate per window (windows containing < 2 fixes with
accuracy <= ACC_M) for the C5 fail-direction decision.

Usage: compute_calibration.py <csv-or-directory>... [--json out.json]
Self-test (synthetic, never evidence): compute_calibration.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WINDOWS_S = (90, 120, 145)
THRESHOLDS_M = tuple(range(20, 41))
SLIDE_STEP_S = 15
ACC_M = 75
JITTER_MARGIN = 1.2
CREEP_MARGIN = 0.8
MIN_SESSIONS = 10
MIN_PARKED_SECONDS = 30 * 60
MIN_CONGESTION_SECONDS = 20 * 60


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        raise ValueError("empty distribution")
    index = (len(sorted_values) - 1) * fraction
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return sorted_values[low]
    weight = index - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def load_sessions(paths: list[Path]) -> dict[str, dict]:
    sessions: dict[str, dict] = {}
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("**/*.csv")))
        else:
            files.append(path)
    for file in files:
        with file.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                session = sessions.setdefault(
                    row["session_id"],
                    {
                        "corpus": row["corpus"],
                        "environment": row["environment"],
                        "device": row["device_model"],
                        "fixes": [],
                    },
                )
                accuracy = row.get("accuracy_m", "")
                session["fixes"].append(
                    (
                        datetime.fromisoformat(row["recorded_at"]),
                        float(row["latitude"]),
                        float(row["longitude"]),
                        float(accuracy) if accuracy else None,
                    )
                )
    for session in sessions.values():
        session["fixes"].sort(key=lambda fix: fix[0])
    return sessions


def window_displacements(session: dict, window_s: int) -> tuple[list[float], int, int]:
    """Sliding-window net displacement; returns (values, fix_poor, total)."""
    fixes = [f for f in session["fixes"]]
    if len(fixes) < 2:
        return [], 0, 0
    start, end = fixes[0][0], fixes[-1][0]
    values: list[float] = []
    fix_poor = 0
    total = 0
    cursor = start
    while cursor + timedelta(seconds=window_s) <= end:
        window_end = cursor + timedelta(seconds=window_s)
        inside = [f for f in fixes if cursor <= f[0] <= window_end]
        usable = [f for f in inside if f[3] is None or f[3] <= ACC_M]
        total += 1
        if len(usable) < 2:
            fix_poor += 1
        else:
            first, last = usable[0], usable[-1]
            values.append(haversine_m(first[1], first[2], last[1], last[2]))
        cursor += timedelta(seconds=SLIDE_STEP_S)
    return values, fix_poor, total


def evaluate(sessions: dict[str, dict]) -> dict:
    report: dict = {"corpora": {}, "windows": {}, "accepted_pairs": [], "coverage": {}}
    for corpus, minimum_seconds in (("parked", MIN_PARKED_SECONDS), ("congestion", MIN_CONGESTION_SECONDS)):
        rows = {k: s for k, s in sessions.items() if s["corpus"] == corpus}
        durations = [
            (s["fixes"][-1][0] - s["fixes"][0][0]).total_seconds() if len(s["fixes"]) > 1 else 0
            for s in rows.values()
        ]
        report["coverage"][corpus] = {
            "sessions": len(rows),
            "sessions_meeting_duration": sum(1 for d in durations if d >= minimum_seconds),
            "devices": sorted({s["device"] for s in rows.values()}),
            "environments": sorted({s["environment"] for s in rows.values()}),
            "minimum_sessions_required": MIN_SESSIONS,
        }
    for window in WINDOWS_S:
        parked_values: list[float] = []
        creep_values: list[float] = []
        fix_poor = 0
        total_windows = 0
        for session in sessions.values():
            values, poor, total = window_displacements(session, window)
            fix_poor += poor
            total_windows += total
            if session["corpus"] == "parked":
                parked_values.extend(values)
            else:
                creep_values.extend(values)
        if not parked_values or not creep_values:
            report["windows"][window] = {"error": "insufficient data"}
            continue
        parked_values.sort()
        creep_values.sort()
        stats = {
            "jitter_p50": percentile(parked_values, 0.50),
            "jitter_p95": percentile(parked_values, 0.95),
            "jitter_p99": percentile(parked_values, 0.99),
            "creep_p05": percentile(creep_values, 0.05),
            "creep_p10": percentile(creep_values, 0.10),
            "fix_poor_rate": (fix_poor / total_windows) if total_windows else None,
            "parked_windows": len(parked_values),
            "congestion_windows": len(creep_values),
        }
        report["windows"][window] = stats
        for threshold in THRESHOLDS_M:
            if stats["jitter_p95"] * JITTER_MARGIN <= threshold <= stats["creep_p05"] * CREEP_MARGIN:
                report["accepted_pairs"].append({"window_s": window, "threshold_m": threshold})
    return report


def synthetic_self_test() -> dict[str, dict]:
    """TOOL-SELF-TEST ONLY: synthetic traces proving the pipeline math.

    Never evidence. Parked = gaussian-ish jitter around one point; creep =
    steady 0.8 km/h drift. Deterministic (no RNG): jitter uses a fixed
    residue pattern.
    """
    base_time = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    sessions: dict[str, dict] = {}
    jitter_pattern_m = [0, 4, 9, 6, 2, 11, 7, 3, 8, 5]
    for n in range(1, 11):
        fixes = []
        for i in range(0, MIN_PARKED_SECONDS + 1, 12):
            offset = jitter_pattern_m[(i // 12 + n) % len(jitter_pattern_m)]
            fixes.append(
                (
                    base_time + timedelta(seconds=i),
                    9.05 + (offset / 111_320.0),
                    7.49,
                    20.0,
                )
            )
        sessions[f"P1-S{n:02d}"] = {
            "corpus": "parked",
            "environment": ["open_sky", "street_canyon", "under_bridge"][n % 3],
            "device": ["Pixel-7", "iPhone-13", "Galaxy-A54"][n % 3],
            "fixes": fixes,
        }
    speed_m_s = 0.8 * 1000 / 3600
    for n in range(1, 11):
        fixes = []
        for i in range(0, MIN_CONGESTION_SECONDS + 1, 12):
            fixes.append(
                (
                    base_time + timedelta(seconds=i),
                    9.10 + (speed_m_s * i / 111_320.0),
                    7.45,
                    15.0,
                )
            )
        sessions[f"P2-S{n:02d}"] = {
            "corpus": "congestion",
            "environment": f"segment-{n % 3}",
            "device": ["Pixel-7", "iPhone-13", "Galaxy-A54"][n % 3],
            "fixes": fixes,
        }
    return sessions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        sessions = synthetic_self_test()
        print("TOOL-SELF-TEST: synthetic sessions — output is NOT evidence")
    elif args.paths:
        sessions = load_sessions(args.paths)
    else:
        parser.error("provide capture CSV paths or --self-test")
    report = evaluate(sessions)
    print(json.dumps(report, indent=2, default=str))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str))
    for corpus, coverage in report["coverage"].items():
        if coverage["sessions_meeting_duration"] < coverage["minimum_sessions_required"]:
            print(f"FAIL-CLOSED: {corpus} corpus below minimum coverage", file=sys.stderr)
            return 2
    if not report["accepted_pairs"]:
        print(
            "FAIL-CLOSED: no (window, threshold) pair satisfies P3 — escalate to the "
            "owner with the measured distributions (Option B/C remain selectable)",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
