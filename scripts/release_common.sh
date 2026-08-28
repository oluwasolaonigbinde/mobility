#!/usr/bin/env bash

set -Eeuo pipefail

readonly RELEASE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly RELEASE_COMPOSE_FILE="${RELEASE_COMPOSE_FILE:-${RELEASE_REPO_ROOT}/docker-compose.production.yml}"

release_log() {
  local event="$1"
  local status="$2"
  local timestamp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"timestamp":"%s","event":"%s","status":"%s"}\n' \
    "${timestamp}" "${event}" "${status}"
}

release_env_value() {
  local env_file="$1"
  local name="$2"
  python3 - "${env_file}" "${name}" <<'PY'
import sys
from pathlib import Path

path, name = sys.argv[1:]
matches = []
for raw_line in Path(path).read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key == name:
        matches.append(value)
if len(matches) != 1:
    raise SystemExit(f"{name} must appear exactly once in the environment file")
print(matches[0])
PY
}

release_require_commands() {
  local command
  for command in "$@"; do
    command -v "${command}" >/dev/null \
      || { echo "ERROR: required command is unavailable: ${command}" >&2; exit 2; }
  done
}

release_stage_done() {
  local state_file="$1"
  local stage="$2"
  jq -e --arg stage "${stage}" '.stages | index($stage) != null' "${state_file}" >/dev/null
}
