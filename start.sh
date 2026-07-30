#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# Agent Xi 一键启动脚本 (Linux / macOS / Git Bash)
# ═══════════════════════════════════════════════════
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── 颜色 ───────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

log()  { echo -e "${CYAN}[Xi]${NC} $1"; }
warn() { echo -e "${RED}[Xi]${NC} $1"; }

# ── 检查 .env ─────────────────────────────────────
if [ ! -f ".env" ]; then
    log "未找到 .env，从 .env.example 复制..."
    cp .env.example .env
    warn "请编辑 .env 填入 API Key 后重新运行"
    exit 1
fi

# ── 安装依赖（仅首次）─────────────────────────────
if [ ! -d ".venv" ]; then
    log "创建虚拟环境..."
    python3 -m venv .venv
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev]" -q
fi

if [ ! -d "web/node_modules" ]; then
    log "安装前端依赖..."
    cd web && npm install --silent && cd ..
fi

# ── 检查前端构建 ──────────────────────────────────
if [ ! -f "web/dist/index.html" ]; then
    log "前端未构建，正在构建..."
    cd web && npm run build && cd ..
fi

# ── 模式选择 ──────────────────────────────────────
MODE="${1:-prod}"

case "$MODE" in
    dev)
        echo ""
        echo -e "  ${GREEN}╔══════════════════════════════════════╗${NC}"
        echo -e "  ${GREEN}║   Agent Xi — 开发模式                ║${NC}"
        echo -e "  ${GREEN}║  后端: http://localhost:9731          ║${NC}"
        echo -e "  ${GREEN}║  前端: http://localhost:5180 (热更新) ║${NC}"
        echo -e "  ${GREEN}╚══════════════════════════════════════╝${NC}"
        echo ""

        # 后台启动后端
        .venv/bin/python -m agent_xi.server --host 0.0.0.0 --port 9731 &
        BACKEND_PID=$!
        trap "kill $BACKEND_PID 2>/dev/null; exit" INT TERM

        sleep 2
        log "后端已启动 (PID: $BACKEND_PID)"

        # 前台启动前端 dev server
        cd web && npm run dev
        ;;
    *)
        echo ""
        echo -e "  ${GREEN}╔═══════════════════════════════════╗${NC}"
        echo -e "  ${GREEN}║     Agent Xi Server              ║${NC}"
        echo -e "  ${GREEN}║  后端: http://localhost:9731      ║${NC}"
        echo -e "  ${GREEN}║  Web UI 已内嵌，无需额外启动       ║${NC}"
        echo -e "  ${GREEN}╚═══════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${DIM}提示: 运行 ./start.sh dev 进入开发模式（前端热更新）${NC}"
        echo ""

        .venv/bin/python -m agent_xi.server --host 0.0.0.0 --port 9731
        ;;
esac
