#!/bin/bash
# 剪映 Agent 启动脚本
mkdir -p data
nohup python3 server.py >> data/log.log 2>&1 &
echo $! > ./server.pid
echo "✅ 服务已启动 (PID: $!)"
echo "访问: http://localhost:5001"




