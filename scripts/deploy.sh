#!/usr/bin/env bash
# deploy.sh — build, test, sync e aguarda o deploy no Northflank.
#
# Uso:
#   ./scripts/deploy.sh                  # full deploy
#   ./scripts/deploy.sh --skip-tests     # pula pytest + tsc (mais rápido)
#   ./scripts/deploy.sh --no-wait        # não aguarda build terminar
#
# O que faz:
#   1. Roda pytest no backend
#   2. Faz push para testebackstage2 (origin/main)
#   3. Faz push para catalogoservico (public-origin/snapmaker3d-studio) → aciona Northflank
#   4. Monitora /health até git_commit mudar (ou timeout 10 min)
set -euo pipefail

HEALTH_URL="https://app.euachei3d.com.br/api/v1/health"
TIMEOUT_SECS=600   # 10 minutos
POLL_INTERVAL=15   # verifica a cada 15s

SKIP_TESTS=false
NO_WAIT=false

for arg in "$@"; do
  case $arg in
    --skip-tests) SKIP_TESTS=true ;;
    --no-wait)    NO_WAIT=true ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── Cores ──────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
err()  { echo -e "${RED}❌ $*${NC}"; exit 1; }

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SnapMaker3d Studio — Deploy Automático"
echo "═══════════════════════════════════════════════════════"

# ── 1. Activate venv ───────────────────────────────────────
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# ── 2. Testes ─────────────────────────────────────────────
if [ "$SKIP_TESTS" = false ]; then
  echo ""
  echo "1. Rodando testes backend..."
  if python -m pytest backend/tests/ -q --tb=short 2>&1 | tail -5; then
    ok "Testes passaram"
  else
    err "Testes falharam — deploy abortado"
  fi
else
  warn "Testes ignorados (--skip-tests)"
fi

# ── 3. Capturar commit atual em produção ──────────────────
echo ""
echo "2. Estado atual de produção..."
CURRENT_COMMIT=$(curl -s "$HEALTH_URL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('git_commit','NONE'))" 2>/dev/null || echo "NONE")
TARGET_COMMIT=$(git rev-parse --short HEAD)
echo "   Produção: ${CURRENT_COMMIT}"
echo "   Local:    ${TARGET_COMMIT}"

if [ "$CURRENT_COMMIT" = "$TARGET_COMMIT" ]; then
  ok "Produção já está no commit $TARGET_COMMIT — nada a fazer"
  exit 0
fi

# ── 4. Push para origin (testebackstage2) ─────────────────
echo ""
echo "3. Push → origin/main (GitHub)..."
git push origin main 2>&1 | tail -3 && ok "Push origin concluído"

# ── 5. Push para catalogoservico (trigger Northflank) ─────
echo ""
echo "4. Push → catalogoservico/snapmaker3d-studio (Northflank)..."
git push public-origin HEAD:snapmaker3d-studio 2>&1 | tail -3 && ok "Push catalogoservico concluído — Northflank buildando..."

if [ "$NO_WAIT" = true ]; then
  warn "Pulando monitoramento (--no-wait)"
  echo ""
  echo "Verifique manualmente com:"
  echo "  curl -s $HEALTH_URL | python3 -m json.tool"
  exit 0
fi

# ── 6. Aguardar build ─────────────────────────────────────
echo ""
echo "5. Aguardando build no Northflank (até ${TIMEOUT_SECS}s)..."
echo "   Monitorando git_commit: ${CURRENT_COMMIT} → ${TARGET_COMMIT}"
echo ""

ELAPSED=0
SPIN=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
SPIN_IDX=0

while [ $ELAPSED -lt $TIMEOUT_SECS ]; do
  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))

  DEPLOYED=$(curl -s --max-time 5 "$HEALTH_URL" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('git_commit','BUILDING'))
except:
    print('UNREACHABLE')
" 2>/dev/null || echo "UNREACHABLE")

  SPIN_CHAR="${SPIN[$SPIN_IDX]}"
  SPIN_IDX=$(( (SPIN_IDX + 1) % 10 ))

  printf "\r   %s  [%3ds] produção em: %-20s" "$SPIN_CHAR" "$ELAPSED" "$DEPLOYED"

  if [ "$DEPLOYED" = "$TARGET_COMMIT" ]; then
    echo ""
    echo ""
    ok "Deploy concluído! Commit $TARGET_COMMIT está em produção."
    echo ""
    echo "   Health completo:"
    curl -s "$HEALTH_URL" | python3 -m json.tool
    echo ""
    exit 0
  fi
done

echo ""
echo ""
warn "Timeout — build não concluiu em ${TIMEOUT_SECS}s"
echo "   Último estado: $DEPLOYED"
echo ""
echo "   Verifique o Northflank em https://app.northflank.com"
echo "   Health: curl -s $HEALTH_URL | python3 -m json.tool"
exit 1
