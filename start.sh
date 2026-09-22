#!/bin/bash
# 剪映 Agent 启动脚本
cd "$(dirname "$0")" || exit 1
PYTHON_BIN=python3
if [ -x .venv/bin/python ]; then
    PYTHON_BIN=.venv/bin/python
fi
mkdir -p data
nohup "$PYTHON_BIN" server.py >> data/log.log 2>&1 &
echo $! > ./server.pid
echo "✅ 服务已启动 (PID: $!)"
echo "访问: http://localhost:5001"



