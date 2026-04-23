#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if [[ "$PYTHON_VERSION" != "3.12" && "$PYTHON_VERSION" != "3.13" ]]; then
  echo "Backend FastAPI requer Python 3.12 ou 3.13 para instalar FastAPI/Pydantic com suporte estável."
  echo "Versão detectada: $PYTHON_VERSION"
  echo "Defina PYTHON_BIN apontando para um Python compatível e execute novamente."
  exit 1
fi

cd "$ROOT_DIR/backend"
"$PYTHON_BIN" -m venv .venv
.venv/bin/pip install -r requirements.txt

cd "$ROOT_DIR/frontend"
npm install

echo "Dependências instaladas."
