#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SNAP_DIR="$ROOT_DIR/tests/snapshots"
PATHS_JSON="$SNAP_DIR/openapi_paths.json"
HASH_TXT="$SNAP_DIR/openapi_sha256.txt"

tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

# Dump full OpenAPI sorted JSON
poetry run python scripts/dump_openapi.py | jq -S '.' > "$tmpfile"

# Update paths snapshot
jq '.paths | keys' "$tmpfile" > "$PATHS_JSON"

# Update hash snapshot
sha256sum "$tmpfile" | awk '{print $1}' > "$HASH_TXT"

echo "Updated:"
echo " - $PATHS_JSON"
echo " - $HASH_TXT"
