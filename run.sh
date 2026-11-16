#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[BidGuard] 正在创建 Python 虚拟环境并安装依赖..."
  python3 -m venv .venv
  .venv/bin/pip install -e .
fi

if [ ! -f "frontend/dist/index.html" ]; then
  echo "[BidGuard] 正在构建前端静态资源..."
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

PORT="${PORT:-8000}"
echo "[BidGuard] 启动标书自动检查工作台 -> http://127.0.0.1:${PORT}"
exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port "${PORT}"
