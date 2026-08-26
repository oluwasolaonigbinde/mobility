#!/usr/bin/env bash

set -Eeuo pipefail

readonly DB_SERVICE="db"
readonly DB_NAME="mobility"
readonly DB_USER="mobility"
readonly RETAIN_COUNT=14
readonly RETAIN_DAYS="${BACKUP_RETENTION_DAYS:-35}"
readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
readonly UTC_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly BACKUP_FILE="${BACKUP_DIR}/mobility_${UTC_TIMESTAMP}.dump"
readonly PARTIAL_FILE="${BACKUP_FILE}.partial"

if ! [[ "${RETAIN_DAYS}" =~ ^[0-9]+$ ]] || (( RETAIN_DAYS < 1 || RETAIN_DAYS > 35 )); then
  echo "BACKUP_RETENTION_DAYS must be an integer from 1 through 35." >&2
  exit 2
fi
readonly RETAIN_MINUTES=$(( RETAIN_DAYS * 24 * 60 ))

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

while IFS= read -r -d '' expired_backup; do
  rm -f -- "${expired_backup}"
  echo "Pruned expired backup: ${expired_backup}"
done < <(
  find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'mobility_*.dump' \
    -mmin "+${RETAIN_MINUTES}" -print0
)

trap - EXIT
echo "Backup complete: ${BACKUP_FILE}"
echo "Retention: at most ${RETAIN_COUNT} local dumps and never over ${RETAIN_DAYS} days."
echo "Copy critical backups only to an approved encrypted destination with the same age bound."
