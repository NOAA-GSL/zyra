#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SNAP_DIR="$ROOT_DIR/tests/snapshots"
PATHS_JSON="$SNAP_DIR/openapi_paths.json"
HASH_TXT="$SNAP_DIR/openapi_sha256.txt"

mkdir -p "$SNAP_DIR"

tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

# Dump full OpenAPI JSON (sorted keys for stability)
if command -v jq >/dev/null 2>&1; then
  poetry run python scripts/dump_openapi.py | jq -S '.' > "$tmpfile"
  # Update paths snapshot
  jq '.paths | keys' "$tmpfile" > "$PATHS_JSON"
  # Compute normalized hash matching tests (remove info.version)
  if command -v sha256sum >/dev/null 2>&1; then
    jq 'del(.info.version)' "$tmpfile" | sha256sum | awk '{print $1}' > "$HASH_TXT"
  else
    # Pass the temporary JSON file as argv[1] to the Python script
    python - "$tmpfile" << 'PY' > "$HASH_TXT"
import copy, json, hashlib, sys
from pathlib import Path
tmp = Path(sys.argv[1])
spec = json.loads(tmp.read_text())
# Work on a deep copy to avoid side effects if spec is reused later.
spec2 = copy.deepcopy(spec)
if isinstance(spec2.get('info'), dict):
    spec2['info'].pop('version', None)
s = json.dumps(spec2, sort_keys=True, separators=(',', ':'))
print(hashlib.sha256(s.encode()).hexdigest())
PY
  fi
else
  # Fallback without jq: do everything in Python
  python - << 'PY'
import copy, json, hashlib
from pathlib import Path
from zyra.api.server import app
spec = app.openapi()
paths = sorted(list((spec.get('paths') or {}).keys()))
snap_dir = Path("tests/snapshots")
snap_dir.mkdir(parents=True, exist_ok=True)
(snap_dir / 'openapi_paths.json').write_text(json.dumps(paths, indent=2) + "\n")
spec2 = copy.deepcopy(spec)
if isinstance(spec2.get('info'), dict):
    spec2['info'].pop('version', None)
js = json.dumps(spec2, sort_keys=True, separators=(',',':'))
digest = hashlib.sha256(js.encode()).hexdigest()
(snap_dir / 'openapi_sha256.txt').write_text(digest + "\n")
print('Updated snapshots (python fallback). SHA=', digest)
PY
fi

echo "Updated:"
echo " - $PATHS_JSON"
echo " - $HASH_TXT"
