#!/bin/bash
# 用法：send.sh "听泉的回复内容"
# 或：  send.sh --user "用户说的话"
ROLE="assistant"
CONTENT="$1"

if [ "$1" = "--user" ]; then
    ROLE="user"
    CONTENT="$2"
fi

if [ -z "$CONTENT" ]; then
    echo "用法: send.sh \"回复内容\""
    echo "      send.sh --user \"用户消息\""
    exit 1
fi

curl -s -X POST http://localhost:19100/send \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"${ROLE}\",\"content\":$(echo "$CONTENT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
  > /dev/null 2>&1
