#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# SessionStart hook: install the repo's git hooks in a fresh checkout.
#
# .pre-commit-config.yaml already declares `require-dco-signoff`, but a
# remote session clones the repo fresh into a container where nothing
# has run `pre-commit install`, so .git/hooks/ is empty and the check
# never fires. Commits then reach the PR before the DCO app rejects
# them, which costs a force-push and invalidates review anchors.
#
# This installs the commit-msg hook directly rather than shelling out
# to `pre-commit`: check_dco_signoff.sh is a dependency-free bash
# script, so wiring it needs neither pre-commit nor a working Poetry
# environment. The other hooks in .pre-commit-config.yaml DO call
# `poetry run`, which is why they are deliberately not installed here
# (see the note in AGENTS.md).
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CHECK="$ROOT/scripts/check_dco_signoff.sh"
HOOK_DIR="$(git -C "$ROOT" rev-parse --git-path hooks 2>/dev/null || echo ".git/hooks")"
# `--git-path` reports relative to the repo root even under `-C`, so a
# session started anywhere but the root would otherwise test and write
# through a path resolved against the wrong directory. `--path-format`
# would do this, but it needs git 2.31; this does not.
case "$HOOK_DIR" in
  /*) ;;
  *) HOOK_DIR="$ROOT/$HOOK_DIR" ;;
esac
HOOK="$HOOK_DIR/commit-msg"
MARKER="zyra-dco-signoff-hook"

if [[ ! -f "$CHECK" ]]; then
  echo "session-start: $CHECK not found; skipping git hook install" >&2
  exit 0
fi

# Never clobber a hook this script did not write (a developer's own
# commit-msg hook, or pre-commit's, both of which already do the job).
if [[ -e "$HOOK" ]] && ! grep -q "$MARKER" "$HOOK" 2>/dev/null; then
  echo "session-start: $HOOK already exists and is not ours; leaving it alone" >&2
  exit 0
fi

mkdir -p "$HOOK_DIR"
cat > "$HOOK" <<HOOK_EOF
#!/usr/bin/env bash
# $MARKER — installed by .claude/hooks/session-start.sh
exec "\$(git rev-parse --show-toplevel)/scripts/check_dco_signoff.sh" "\$@"
HOOK_EOF
chmod +x "$HOOK"
echo "session-start: installed DCO commit-msg hook at $HOOK"
