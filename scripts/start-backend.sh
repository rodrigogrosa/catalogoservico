#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Ambiente virtual nao encontrado em backend/.venv. Execute ./scripts/bootstrap.sh primeiro."
  exit 1
fi

.venv/bin/python run.py
