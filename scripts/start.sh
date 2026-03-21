#!/bin/bash
set -e

cd "$(dirname "$0")/.."
VENV_DIR="./venv"

echo "=== VoiceKB 启动 ==="

# 激活 venv
source "$VENV_DIR/bin/activate"

# 确保包可导入
export PYTHONPATH="$PWD/src:$PYTHONPATH"

# 确保目录存在
mkdir -p data/{uploads,transcripts,chroma,logs}

# 启动 FastAPI
echo "启动 VoiceKB 服务 (port ${VOICEKB_PORT:-8080})..."
exec uvicorn voicekb.api.app:app \
  --host 0.0.0.0 \
  --port "${VOICEKB_PORT:-8080}" \
  --workers 1 \
  --log-level info
