#!/bin/bash
# 剪映 Agent 停止脚本

PID_FILE="./server.pid"

# 检查 PID 文件是否存在
if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  服务未运行 (未找到 PID 文件)"
    exit 0
fi

# 读取 PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "⚠️  进程不存在 (PID: $PID)"
    rm -f "$PID_FILE"
    exit 0
fi

# 停止进程
echo "🛑 正在停止服务 (PID: $PID)..."
kill "$PID"

# 等待进程结束
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ 服务已停止"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 如果进程仍未结束，强制杀死
echo "⚠️  进程未响应，强制停止..."
kill -9 "$PID" 2>/dev/null
rm -f "$PID_FILE"
echo "✅ 服务已强制停止"

