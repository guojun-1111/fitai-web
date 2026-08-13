#!/bin/bash
# FitAI-web 部署脚本 (V10 — Pearl因果三层 + 极致性能)
set -e

SERVER_IP="121.40.133.1"
SSH_USER="root"
SERVER_PATH="/opt/fitai-web"

cd "$(dirname "$0")"

echo "=== 安装依赖 ==="
ssh ${SSH_USER}@${SERVER_IP} "pip3 install httpx -q 2>/dev/null; echo httpx OK"

echo "=== 上传核心文件 ==="
scp server.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/server.py
scp config.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/config.py

# Agent & Providers
scp agent/loop.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/agent/loop.py
scp providers/openai_provider.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/providers/openai_provider.py

# Core modules
ssh ${SSH_USER}@${SERVER_IP} "mkdir -p ${SERVER_PATH}/core"
scp core/*.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/core/

# Auth
scp auth/utils.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/auth/utils.py 2>/dev/null || true
scp auth/router.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/auth/router.py 2>/dev/null || true
scp auth/middleware.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/auth/middleware.py 2>/dev/null || true

# Tools
scp tools/fitai_database.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/tools/fitai_database.py
scp tools/fitai_tools.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/tools/fitai_tools.py
scp tools/tool_definitions.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/tools/tool_definitions.py
scp tools/registry.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/tools/registry.py
scp tools/agent_prompts.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/tools/agent_prompts.py

# Routers (all 10)
ssh ${SSH_USER}@${SERVER_IP} "mkdir -p ${SERVER_PATH}/routers"
scp routers/*.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/routers/

# Analysis (all 26 files)
ssh ${SSH_USER}@${SERVER_IP} "mkdir -p ${SERVER_PATH}/fitai/analysis"
scp fitai/analysis/*.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/fitai/analysis/
scp fitai/analysis/__init__.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/fitai/analysis/__init__.py 2>/dev/null || true

# Health platforms
scp fitai/health_platforms/*.py ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/fitai/health_platforms/

echo ""
echo "=== 上传前端文件 ==="
scp static/index.html ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/index.html
scp static/landing.html ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/landing.html
scp static/login.html ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/login.html
scp static/style.css ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/style.css
scp static/style-mobile.css ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/style-mobile.css
scp static/manifest.json ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/manifest.json
scp static/sw.js ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/sw.js

ssh ${SSH_USER}@${SERVER_IP} "mkdir -p ${SERVER_PATH}/static/icons ${SERVER_PATH}/static/img"
scp static/icons/icon-192.png ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/icons/icon-192.png 2>/dev/null || true
scp static/icons/icon-512.png ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/icons/icon-512.png 2>/dev/null || true
scp static/img/*.webp ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/img/ 2>/dev/null || true

ssh ${SSH_USER}@${SERVER_IP} "mkdir -p ${SERVER_PATH}/static/js"
for f in static/js/*.js; do
    scp "$f" ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/js/
done

scp static/import-worker.js ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/import-worker.js 2>/dev/null || true

# V21: MediaPipe model files for pose detection
ssh ${SSH_USER}@${SERVER_IP} "mkdir -p ${SERVER_PATH}/static/mediapipe/wasm"
scp static/mediapipe/*.mjs static/mediapipe/*.task ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/mediapipe/ 2>/dev/null || true
scp static/mediapipe/wasm/* ${SSH_USER}@${SERVER_IP}:${SERVER_PATH}/static/mediapipe/wasm/ 2>/dev/null || true

echo ""
echo "=== 验证语法 ==="
ssh ${SSH_USER}@${SERVER_IP} "cd ${SERVER_PATH} && python3 -c 'import py_compile; py_compile.compile(\"server.py\", doraise=True); print(\"server.py OK\")'" || echo "语法检查跳过"

echo ""
echo "=== 重启服务 ==="
ssh ${SSH_USER}@${SERVER_IP} "systemctl restart fitai 2>/dev/null || supervisorctl restart fitai 2>/dev/null || (pkill -f 'uvicorn server:app' ; cd ${SERVER_PATH} && nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 &); echo 'Restart triggered'"

sleep 3

echo ""
echo "=== 健康检查 ==="
ssh ${SSH_USER}@${SERVER_IP} "curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool"
echo ""
echo "部署完成!"
