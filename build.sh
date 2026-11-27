#!/usr/bin/env sh
# Build a self-contained player page from a script, its data and an optional theme.
#
# Usage: ./build.sh [SCRIPT_ID] [OPTIONS]
#   SCRIPT_ID   the script to build (default: year-wrapped)
#   OPTIONS     passed straight to `team-wrapped build`:
#                 --data FOLDER   data folder under the repo root (default: data; try data-sample)
#                 --theme NAME    theme to apply (default: the script's `theme:`, else the built-in look)
#                 --out FOLDER    output folder under the repo root (default: dist)
#
# Examples:
#   ./build.sh
#   ./build.sh year-wrapped --data data-sample
#   ./build.sh year-wrapped --data data --theme my-brand
#
# The page is written to dist/<SCRIPT_ID>/index.html. Open it in a browser, or run
#   python3 -m http.server 8000 --directory dist/<SCRIPT_ID>
set -eu

# Always run from the repository root, wherever the script is called from.
cd "$(dirname "$0")"

SCRIPT_ID="${1:-year-wrapped}"
if [ "$#" -gt 0 ]; then
  shift
fi

PYTHONPATH=src exec python3 -m team_wrapped build "$SCRIPT_ID" "$@"
