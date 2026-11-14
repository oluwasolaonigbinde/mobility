"""D32 changed-line coverage against a base commit, from LCOV (tracked diffs + untracked files)."""

import re
import subprocess
import sys
from collections import defaultdict

BASE, LCOV, PREFIX, ROOT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
# PREFIX: repo-relative path prefix that LCOV SF paths are relative to ("" or "frontend/").


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


changed: dict[str, set[int]] = defaultdict(set)
file_diff = None
for line in git("diff", "-U0", BASE, "--", ".").splitlines():
    if line.startswith("+++ "):
        file_diff = line[6:] if line != "+++ /dev/null" else None
    elif line.startswith("@@") and file_diff:
        m = re.search(r"\+(\d+)(?:,(\d+))?", line)
        start, count = int(m.group(1)), int(m.group(2) or 1)
        changed[file_diff].update(range(start, start + count))
for path in git("ls-files", "--others", "--exclude-standard").splitlines():
    try:
        with open(f"{ROOT}/{path}", encoding="utf-8") as handle:
            changed[path].update(range(1, sum(1 for _ in handle) + 1))
    except (UnicodeDecodeError, IsADirectoryError):
        pass

lines_hit = lines_total = branches_hit = branches_total = 0
report = []
sf = None
da: dict[int, int] = {}
brda: dict[int, list[int]] = defaultdict(list)


def flush():
    global lines_hit, lines_total, branches_hit, branches_total
    if sf is None:
        return
    rel = sf.split(ROOT + "/", 1)[-1] if sf.startswith("/") else PREFIX + sf
    wanted = changed.get(rel)
    if not wanted:
        return
    lh = sum(1 for n in wanted if da.get(n, 0) > 0)
    lt = sum(1 for n in wanted if n in da)
    bh = sum(1 for n in wanted for taken in brda.get(n, []) if taken > 0)
    bt = sum(len(brda.get(n, [])) for n in wanted)
    missed = sorted(n for n in wanted if n in da and da[n] == 0)
    lines_hit += lh
    lines_total += lt
    branches_hit += bh
    branches_total += bt
    report.append((rel, lh, lt, bh, bt, missed))


with open(LCOV, encoding="utf-8") as handle:
    for raw in handle:
        raw = raw.strip()
        if raw.startswith("SF:"):
            flush()
            sf, da, brda = raw[3:], {}, defaultdict(list)
        elif raw.startswith("DA:"):
            n, hits = raw[3:].split(",")[:2]
            da[int(n)] = int(hits)
        elif raw.startswith("BRDA:"):
            n, _block, _branch, taken = raw[5:].split(",")
            brda[int(n)].append(0 if taken == "-" else int(taken))
    flush()

for rel, lh, lt, bh, bt, missed in sorted(report):
    print(f"{rel}: lines {lh}/{lt} branches {bh}/{bt} missed {missed[:25]}")
pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"  # noqa: E731
print(
    f"TOTAL lines {lines_hit}/{lines_total} ({pct(lines_hit, lines_total)}) "
    f"branches {branches_hit}/{branches_total} ({pct(branches_hit, branches_total)})"
)
