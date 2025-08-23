#!/bin/bash
set -euo pipefail

WIKI_DIR="/app/docs/source/wiki"
WIKI_REMOTE="https://github.com/NOAA-GSL/zyra.wiki.git"

# Always clone to a temp dir, then rsync into WIKI_DIR excluding .git to avoid nested repos
TMP_DIR=$(mktemp -d)
cleanup() { rm -rf "$TMP_DIR" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Cloning wiki into temp dir..."
git clone "$WIKI_REMOTE" "$TMP_DIR"

echo "Ensuring target directory exists: $WIKI_DIR"
mkdir -p "$WIKI_DIR"

# Remove any historical nested .git directories inside the docs tree
if find "$WIKI_DIR" -mindepth 1 -maxdepth 2 -name .git -type d -print -quit | grep -q .; then
  echo "Removing nested .git directories from $WIKI_DIR"
  find "$WIKI_DIR" -name .git -type d -prune -exec rm -rf {} +
fi

echo "Preparing target directory (delete extras, keep .git)..."
# Delete everything under WIKI_DIR except a top-level .git if present,
# to emulate rsync --delete semantics without requiring rsync
find "$WIKI_DIR" -mindepth 1 -maxdepth 1 -not -name '.git' -exec rm -rf {} +

echo "Copying wiki contents into docs (excluding .git)..."
# Remove the cloned .git to avoid nesting repo metadata
rm -rf "$TMP_DIR/.git"

# Use tar to preserve permissions, symlinks, mtime
tar -C "$TMP_DIR" -cf - . | tar -C "$WIKI_DIR" -xpf -

echo "Wiki sync complete."
