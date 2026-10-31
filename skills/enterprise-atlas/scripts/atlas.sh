#!/usr/bin/env bash
# Enterprise Atlas engine wrapper. Works from any directory; data lives in a workspace
# folder next to where you run it (default ./atlas-workspace, override with ATLAS_HOME).
#
#   atlas.sh init                 create the workspace (needle/, web/, procurement/)
#   atlas.sh import [PATHS...]    import harvested files (default: the whole workspace) and rebuild
#   atlas.sh summary              graph size + best candidate per buying role
#   atlas.sh report               full org tree + buying committee
#   atlas.sh serve [PORT]         UI at http://localhost:8787 (auto-refreshes when data changes)
#   atlas.sh demo                 import everything, print the summary, start the UI
#   atlas.sh export-site DIR [--no-redact]   static site
#   atlas.sh <any atlas.cli command>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV="${ATLAS_VENV:-$ROOT/.venv}"
WS="${ATLAS_HOME:-$PWD/atlas-workspace}"
if [ ! -x "$VENV/bin/python" ]; then
  echo "· first run: creating virtualenv in $VENV" >&2
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$ROOT/engine/requirements.txt"
fi
mkdir -p "$WS/needle" "$WS/web" "$WS/procurement"
export ATLAS_DB="${ATLAS_DB:-$WS/atlas.sqlite}"
export PYTHONPATH="$ROOT/engine${PYTHONPATH:+:$PYTHONPATH}"
PY="$VENV/bin/python"
# global flags may come before the command: --problem ID
while [ "${1:-}" = "--problem" ]; do export ATLAS_PROBLEM="$2"; shift 2; done
cmd="${1:-summary}"; shift || true
case "$cmd" in
  init)
    echo "workspace: $WS"; ls -1 "$WS" ;;
  import)
    if [ "$#" -eq 0 ]; then set -- "$WS"; fi
    exec "$PY" -m atlas.cli import "$@" ;;
  serve)
    PORT="${1:-${PORT:-8787}}"
    echo "Atlas UI → http://localhost:$PORT   (db: $ATLAS_DB)"
    exec "$VENV/bin/uvicorn" atlas.api:app --app-dir "$ROOT/engine" --port "$PORT" --log-level warning ;;
  demo)
    "$PY" -m atlas.cli import "$WS"
    PORT="${1:-${PORT:-8787}}"
    echo "Atlas UI → http://localhost:$PORT"
    exec "$VENV/bin/uvicorn" atlas.api:app --app-dir "$ROOT/engine" --port "$PORT" --log-level warning ;;
  *)
    exec "$PY" -m atlas.cli "$cmd" "$@" ;;
esac
