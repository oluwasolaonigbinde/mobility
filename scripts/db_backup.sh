#!/usr/bin/env bash

set -Eeuo pipefail

readonly DB_SERVICE="db"
readonly DB_NAME="mobility"
readonly DB_USER="mobility"
readonly RETAIN_COUNT=14
readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
readonly UTC_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly BACKUP_FILE="${BACKUP_DIR}/mobility_${UTC_TIMESTAMP}.dump"
readonly PARTIAL_FILE="${BACKUP_FILE}.partial"

cleanup() {
  rm -f "${PARTIAL_FILE}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

echo "Creating PostgreSQL custom-format backup: ${BACKUP_FILE}"
docker compose exec -T "${DB_SERVICE}" \
  pg_dump --username="${DB_USER}" --dbname="${DB_NAME}" --format=custom \
  >"${PARTIAL_FILE}"

chmod 600 "${PARTIAL_FILE}"
mv "${PARTIAL_FILE}" "${BACKUP_FILE}"

backup_files=()
while IFS= read -r backup_path; do
  backup_files+=("${backup_path}")
done < <(
  find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'mobility_*.dump' -print0 \
    | xargs -0 ls -1t 2>/dev/null || true
)

if (( ${#backup_files[@]} > RETAIN_COUNT )); then
  for (( index = RETAIN_COUNT; index < ${#backup_files[@]}; index++ )); do
    rm -f -- "${backup_files[index]}"
    echo "Pruned old backup: ${backup_files[index]}"
  done
fi

trap - EXIT
echo "Backup complete: ${BACKUP_FILE}"
echo "Retention: newest ${RETAIN_COUNT} local dumps are kept. Copy critical backups off-host."
