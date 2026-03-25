#!/bin/bash
# VoiceKB 一键部署所有服务
# 用法: ./scripts/deploy-services.sh
#
# 前提：
# 1. llama.cpp 已编译（~/llama.cpp/build/bin/llama-server）
# 2. GGUF 模型已下载（~/models/Qwen3.5-35B-A3B-GGUF/）
# 3. Docker 已安装且有 nvidia runtime
# 4. voicekb venv 已创建且依赖已装

set -e

echo "=== 1. 停止所有服务 ==="
sudo systemctl stop voicekb llm-server whisper-server 2>/dev/null || true
docker stop whisper-server 2>/dev/null || true

echo "=== 2. 确保 whisper Docker 容器存在 ==="
if ! docker ps -a | grep -q whisper-server; then
    echo "创建 whisper-server 容器..."
    docker run -d \
        --name whisper-server \
        --gpus all \
        -p 8000:9000 \
        -e ASR_MODEL=medium \
        -e ASR_ENGINE=faster_whisper \
        --restart unless-stopped \
        onerahmet/openai-whisper-asr-webservice:latest-gpu
    docker stop whisper-server  # 先停，等 systemd 按顺序启动
fi

echo "=== 3. 按顺序启动 ==="
echo "  启动 llm-server (llama.cpp)..."
sudo systemctl start llm-server
sleep 50  # llama.cpp 加载模型需要时间

echo "  启动 whisper-server (Docker)..."
sudo systemctl start whisper-server
sleep 10

echo "  启动 voicekb..."
sudo systemctl start voicekb
sleep 3

echo "=== 4. 验证 ==="
echo -n "  LLM:     "; curl -s http://localhost:18090/v1/models > /dev/null && echo "OK" || echo "FAIL"
echo -n "  Whisper:  "; curl -s http://localhost:8000/v1/models > /dev/null && echo "OK" || echo "FAIL"
echo -n "  VoiceKB:  "; curl -s http://localhost:18089/api/health > /dev/null && echo "OK" || echo "FAIL"

echo ""
echo "=== GPU 使用情况 ==="
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
nvidia-smi --query-compute-apps=pid,name,used_gpu_memory --format=csv,noheader

echo ""
echo "=== 完成 ==="
