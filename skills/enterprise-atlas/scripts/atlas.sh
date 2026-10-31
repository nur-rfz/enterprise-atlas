#!/usr/bin/env bash
# Run the Enterprise Atlas engine from anywhere. Creates the virtualenv on first use.
#   atlas.sh build | import FILES | harvest-needle | harvest-web URLS | harvest-ted | report | export-site DIR | serve
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV="${ATLAS_VENV:-$ROOT/.venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$ROOT/engine/requirements.txt"
fi
export ATLAS_DB="${ATLAS_DB:-$ROOT/data/atlas.sqlite}"
cd "$ROOT/engine"
if [ "${1:-}" = "serve" ]; then
  exec "$VENV/bin/uvicorn" atlas.api:app --port "${PORT:-8787}"
fi
exec "$VENV/bin/python" -m atlas.cli "$@"
