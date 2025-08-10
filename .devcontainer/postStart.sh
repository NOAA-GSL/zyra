#!/usr/bin/env bash
set -euo pipefail

# Options
FORCE_UPDATE=0
REFRESH_SECONDS=${DOCS_REFRESH_SECONDS:-3600} # default 1 hour
while [[ ${1:-} ]]; do
  case "$1" in
    --force) FORCE_UPDATE=1; shift ;;
    --refresh-seconds) REFRESH_SECONDS="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

# Copy default .env if missing
if [[ ! -f .env && -f .devcontainer/.env ]]; then
  echo "[postStart] Seeding .env from .devcontainer/.env"
  cp .devcontainer/.env .env
fi

WIKI_URL="https://github.com/NOAA-GSL/datavizhub.wiki.git"
DOCS_DIR="wiki"
META_FILE="$DOCS_DIR/.mirror_meta"

now_epoch() { date +%s; }

should_update=0
if [[ ! -d "$DOCS_DIR" ]]; then
  echo "[postStart] ${DOCS_DIR} missing; will clone wiki"
  should_update=1
else
  if [[ $FORCE_UPDATE -eq 1 ]]; then
    echo "[postStart] Force update requested"
    should_update=1
  else
    last_sync=0
    if [[ -f "$META_FILE" ]]; then
      # shellcheck disable=SC1090
      source "$META_FILE" || true
      last_sync=${last_sync_epoch:-0}
    fi
    now=$(now_epoch)
    age=$(( now - last_sync ))
    if (( age >= REFRESH_SECONDS )); then
      echo "[postStart] Docs age ${age}s >= ${REFRESH_SECONDS}s; refreshing wiki"
      should_update=1
    else
      echo "[postStart] Docs are fresh (${age}s old); skipping refresh"
    fi
  fi
fi

if [[ $should_update -eq 1 ]]; then
  set +e
  echo "[postStart] Cloning wiki (shallow) into temporary folder"
  tmp_dir="${DOCS_DIR}.new"
  rm -rf "$tmp_dir"
  if git clone --depth=1 "$WIKI_URL" "$tmp_dir"; then
    rm -rf "$tmp_dir/.git"
    echo "source_url=\"$WIKI_URL\"" > "$tmp_dir/.mirror_meta"
    echo "last_sync_epoch=$(now_epoch)" >> "$tmp_dir/.mirror_meta"
    rm -rf "$DOCS_DIR"
    mv "$tmp_dir" "$DOCS_DIR"
    echo "[postStart] Wiki synced to /app/docs"
  else
    echo "[postStart] WARN: Wiki clone failed; leaving existing /app/docs in place" >&2
    rm -rf "$tmp_dir"
  fi
  set -e
fi

exit 0