#!/bin/bash
# 一键启动听泉直播间
cd "$(dirname "$0")"
echo "启动听泉直播间..."
python3 bridge.py &
BRIDGE_PID=$!
sleep 1

# Check if server started
if kill -0 $BRIDGE_PID 2>/dev/null; then
    open http://localhost:19100
    echo "直播间已开启，在 Claude Code 中开始鉴定吧"
    echo "  页面: http://localhost:19100"
    echo "  发送: curl -X POST http://localhost:19100/send -d '{\"role\":\"assistant\",\"content\":\"...\"}'"
    echo "  按 Ctrl+C 关闭"
    wait $BRIDGE_PID
else
    echo "启动失败，请检查端口 19100 是否被占用"
    exit 1
fi
