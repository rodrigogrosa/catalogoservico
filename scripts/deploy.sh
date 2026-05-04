#!/usr/bin/env bash
# deploy.sh — build, test, sync e aguarda o deploy no Northflank.
#
# Uso:
#   ./scripts/deploy.sh                  # full deploy
#   ./scripts/deploy.sh --skip-tests     # pula pytest (mais rápido)
#   ./scripts/deploy.sh --no-wait        # não aguarda build terminar
#
# O que faz:
#   1. Roda pytest no backend
#   2. Faz push para testebackstage2 (origin/main)
#   3. Faz push para catalogoservico (public-origin/snapmaker3d-studio) → aciona Northflank
#   4. Detecta início do build (resposta muda para 503)
#   5. Aguarda o build terminar (503 → 200) e confirma deploy
set -euo pipefail

HEALTH_URL="https://app.euachei3d.com.br/api/v1/health"
TIMEOUT_SECS=600   # 10 minutos
POLL_INTERVAL=10   # verifica a cada 10s

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
  RESULT=$(python -m pytest backend/tests/ -q --tb=short 2>&1 | tail -3)
  echo "   $RESULT"
  if echo "$RESULT" | grep -qE "failed|error"; then
    err "Testes falharam — deploy abortado"
  fi
  ok "Testes passaram"
else
  warn "Testes ignorados (--skip-tests)"
fi

# ── 3. Push ────────────────────────────────────────────────
echo ""
echo "2. Push → origin/main..."
git push origin main 2>&1 | tail -2 && ok "Push origin OK"

echo ""
echo "3. Push → catalogoservico (Northflank trigger)..."
git push public-origin HEAD:snapmaker3d-studio 2>&1 | tail -2 && ok "Push catalogoservico OK — Northflank buildando..."

TARGET_COMMIT=$(git rev-parse --short HEAD)
echo "   Commit: $TARGET_COMMIT"

if [ "$NO_WAIT" = true ]; then
  warn "Pulando monitoramento (--no-wait)"
  echo "  curl -s $HEALTH_URL | python3 -m json.tool"
  exit 0
fi

# ── 4. Detectar início do build (espera 503) ──────────────
echo ""
echo "4. Detectando início do build (aguardando 503)..."
SAW_503=false
for i in $(seq 1 12); do   # até 2 min para começar
  sleep 10
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "0")
  printf "   [%ds] HTTP %s\n" $((i*10)) "$HTTP_CODE"
  if [ "$HTTP_CODE" = "503" ]; then
    SAW_503=true
    ok "Build iniciado (503 detectado)"
    break
  fi
done
if [ "$SAW_503" = false ]; then
  warn "503 não detectado — pode já ter sido rápido ou não há mudanças"
fi

# ── 5. Aguardar 200 após o build ──────────────────────────
echo ""
echo "5. Aguardando backend voltar (200)..."
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT_SECS ]; do
  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$HEALTH_URL" 2>/dev/null || echo "0")
  COMMIT=$(curl -s --max-time 8 "$HEALTH_URL" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('git_commit','?'))" 2>/dev/null || echo "?")
  printf "\r   [%3ds] HTTP %-3s  git_commit=%-15s" "$ELAPSED" "$HTTP_CODE" "$COMMIT"
  if [ "$HTTP_CODE" = "200" ] && [ "$SAW_503" = true ]; then
    echo ""
    echo ""
    ok "Deploy concluído! Backend respondendo (commit=$COMMIT)"
    curl -s "$HEALTH_URL" | python3 -m json.tool
    exit 0
  fi
done

echo ""
warn "Timeout ${TIMEOUT_SECS}s"
echo "  curl -s $HEALTH_URL | python3 -m json.tool"
exit 1

exit 1
