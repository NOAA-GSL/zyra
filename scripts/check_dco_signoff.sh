#!/usr/bin/env bash
set -euo pipefail

# Pre-commit commit-msg hook: verify DCO Signed-off-by is present
# Usage: pre-commit passes the commit message file as $1

if [[ $# -lt 1 ]]; then
  echo "ERROR: Missing commit message file path." >&2
  exit 2
fi

msg_file="$1"

if ! grep -qiE '^Signed-off-by:\s+.+<.+@.+>$' "$msg_file"; then
  echo "ERROR: Commit message missing 'Signed-off-by: Name <email>' line (DCO)." >&2
  echo "Add it automatically with: git commit -s --amend --no-edit" >&2
  echo "Or when creating new commits: git commit -s -m 'your message'" >&2
  exit 1
fi

exit 0

