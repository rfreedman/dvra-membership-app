#!/usr/bin/env bash
# Deploy CGI runtime files to DreamHost via rsync (password auth).
# Does not transfer SQLite DB, var/, .venv, tests, or .env.
#
# Usage:
#   ./scripts/deploy.sh
#   ./scripts/deploy.sh --dry-run
#   ./scripts/deploy.sh -n
set -euo pipefail

HOST=w2zq
REMOTE=/home/dvra/membership-app
DRY_RUN="${DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [--dry-run|-n] [--help|-h]

Deploys to w2zq:/home/dvra/membership-app

Environment:
  SSHPASS   SSH password (prompted if unset)
  DRY_RUN   Set to 1 for dry-run (same as --dry-run)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|-n)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required for password auth." >&2
  echo "  macOS: brew install hudochenkov/sshpass/sshpass" >&2
  echo "  or:    brew install sshpass" >&2
  exit 1
fi

if [[ -z "${SSHPASS:-}" ]]; then
  read -r -s -p "SSH password for ${HOST}: " SSHPASS
  echo
  export SSHPASS
fi
if [[ -z "${SSHPASS}" ]]; then
  echo "No password provided." >&2
  exit 1
fi

# Fail early if expected sources are missing (avoid silent empty syncs).
for path in \
  ./index.py \
  ./.htaccess \
  ./requirements.txt \
  ./dvra \
  ./database \
  ./templates \
  ./static
do
  if [[ ! -e "${path}" ]]; then
    echo "Missing required path: ${path} (cwd=${ROOT})" >&2
    exit 1
  fi
done

RSYNC=(
  sshpass -e rsync
  -avz
  -e "ssh -o StrictHostKeyChecking=accept-new"
  --exclude '__pycache__/'
  --exclude '*.py[cod]'
  --exclude '.DS_Store'
  --exclude '*.sqlite'
  --exclude '*.sqlite3'
  --exclude '*.db'
)

if [[ "${DRY_RUN}" == "1" ]]; then
  RSYNC+=(--dry-run)
  echo "Dry-run: no files will be changed."
fi

echo "Deploying from ${ROOT}"
echo "         to   ${HOST}:${REMOTE}"

"${RSYNC[@]}" --delete ./dvra/      "${HOST}:${REMOTE}/dvra/"
"${RSYNC[@]}" --delete ./database/  "${HOST}:${REMOTE}/database/"
"${RSYNC[@]}" --delete ./templates/ "${HOST}:${REMOTE}/templates/"
"${RSYNC[@]}" --delete ./static/    "${HOST}:${REMOTE}/static/"
"${RSYNC[@]}" ./index.py ./.htaccess ./requirements.txt "${HOST}:${REMOTE}/"

remote_q="$(printf '%q' "${REMOTE}")"
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "Dry-run: would run on ${HOST}: cd ${REMOTE} && chmod 755 index.py && mkdir -p var/sessions"
else
  sshpass -e ssh -o StrictHostKeyChecking=accept-new "${HOST}" \
    "cd ${remote_q} && chmod 755 index.py && mkdir -p var/sessions"
fi

echo "Done."
