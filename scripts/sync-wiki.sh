#!/bin/bash
set -e

WIKI_DIR="/app/docs/source/wiki"
WIKI_REMOTE="https://github.com/NOAA-GSL/zyra.wiki.git"

# Case 1: Wiki already cloned → update
if [ -d "$WIKI_DIR/.git" ]; then
    echo "Updating existing wiki repo..."
    cd "$WIKI_DIR"
    git pull

# Case 2: Placeholder exists → move it aside and clone
elif [ -d "$WIKI_DIR" ]; then
    echo "Found placeholder wiki directory. Moving it to backup..."
    mv "$WIKI_DIR" "${WIKI_DIR}.bak.$(date +%s)"
    git clone "$WIKI_REMOTE" "$WIKI_DIR"

# Case 3: Nothing there → clone fresh
else
    echo "Cloning wiki repo fresh..."
    git clone "$WIKI_REMOTE" "$WIKI_DIR"
fi
