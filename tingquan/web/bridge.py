#!/usr/bin/env python3
"""
听泉鉴宝直播间 — 桥接服务
SSE + HTTP Server, Python 标准库实现, 零依赖

Claude Code 通过 POST /send 发消息 -> SSE 推送给浏览器
GET /         -> serve index.html
GET /events   -> SSE 事件流
GET /bgm/*    -> serve BGM 文件
GET /expr/*   -> serve 表情包文件
"""

import asyncio
import json
import logging
import mimetypes
import os
import time
import urllib.parse
from http import HTTPStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

PORT = 19100
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEB_DIR)
BGM_DIR = os.path.join(PROJECT_DIR, "references", "bgm")
EXPR_DIR = os.path.join(PROJECT_DIR, "references", "expressions")

# ========== SSE Client Registry ==========

class SSEClientRegistry:
    def __init__(self):
        self._clients: list[asyncio.Queue] = []

    def add(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._clients.append(q)
        log.info(f"SSE client connected (total: {len(self._clients)})")
        return q

    def remove(self, q: asyncio.Queue):
        if q in self._clients:
            self._clients.remove(q)
        log.info(f"SSE client disconnected (total: {len(self._clients)})")

    def broadcast(self, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    @property
    def count(self) -> int:
        return len(self._clients)


registry = SSEClientRegistry()

# ========== HTTP Protocol Handler ==========

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle a single HTTP connection."""
    try:
        # Read request line
        request_line = await asyncio.wait_for(reader.readline(), timeout=30)
        if not request_line:
            writer.close()
            return

        request_str = request_line.decode("utf-8", errors="replace").strip()
        parts = request_str.split(" ")
        if len(parts) < 2:
            writer.close()
            return

        method = parts[0].upper()
        raw_path = parts[1]

        # Read headers
        headers = {}
        content_length = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                break
            if ":" in decoded:
                key, val = decoded.split(":", 1)
                headers[key.strip().lower()] = val.strip()
                if key.strip().lower() == "content-length":
                    content_length = int(val.strip())

        # Read body if present
        body = b""
        if content_length > 0:
            body = await asyncio.wait_for(reader.readexactly(content_length), timeout=30)

        # Parse path
        parsed = urllib.parse.urlparse(raw_path)
        path = urllib.parse.unquote(parsed.path)

        # Route
        if method == "POST" and path == "/send":
            await handle_send(writer, body)
        elif method == "GET" and path == "/events":
            await handle_sse(writer)
            return  # SSE keeps connection open, don't close
        elif method == "GET" and path == "/status":
            await handle_status(writer)
        elif method == "GET":
            await handle_static(writer, path)
        elif method == "OPTIONS":
            await send_response(writer, 204, b"", extra_headers=cors_headers())
        else:
            await send_response(writer, 405, b"Method Not Allowed")

    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        log.error(f"Handler error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def handle_send(writer: asyncio.StreamWriter, body: bytes):
    """POST /send — receive message from Claude Code, broadcast to SSE clients."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        await send_json(writer, 400, {"error": "Invalid JSON"})
        return

    role = data.get("role", "assistant")
    content = data.get("content", "")
    if not content:
        await send_json(writer, 400, {"error": "content is required"})
        return

    message = {
        "role": role,
        "content": content,
        "timestamp": time.time(),
    }

    registry.broadcast(message)
    log.info(f"[{role}] {content[:80]}{'...' if len(content) > 80 else ''}")

    await send_json(writer, 200, {"ok": True, "clients": registry.count})


async def handle_sse(writer: asyncio.StreamWriter):
    """GET /events — Server-Sent Events stream."""
    # Send SSE headers
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/event-stream\r\n"
        "Cache-Control: no-cache\r\n"
        "Connection: keep-alive\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "\r\n"
    )
    writer.write(header.encode("utf-8"))
    await writer.drain()

    # Send initial connected event
    await sse_write(writer, "connected", json.dumps({"clients": registry.count + 1}, ensure_ascii=False))

    q = registry.add()
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=15)
                await sse_write(writer, "message", payload)
            except asyncio.TimeoutError:
                # Send keepalive comment
                writer.write(b": keepalive\n\n")
                await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        registry.remove(q)


async def sse_write(writer: asyncio.StreamWriter, event: str, data: str):
    """Write a single SSE event."""
    lines = data.split("\n")
    msg = f"event: {event}\n"
    for line in lines:
        msg += f"data: {line}\n"
    msg += "\n"
    writer.write(msg.encode("utf-8"))
    await writer.drain()


async def handle_status(writer: asyncio.StreamWriter):
    """GET /status — health check."""
    await send_json(writer, 200, {"ready": True, "clients": registry.count})


async def handle_static(writer: asyncio.StreamWriter, path: str):
    """Serve static files: index.html, bgm, expressions."""
    if path == "/" or path == "/index.html":
        file_path = os.path.join(WEB_DIR, "index.html")
    elif path.startswith("/bgm/"):
        filename = path[5:]  # strip /bgm/
        file_path = os.path.join(BGM_DIR, filename)
    elif path.startswith("/expr/"):
        filename = path[6:]  # strip /expr/
        file_path = os.path.join(EXPR_DIR, filename)
    else:
        # Try serving from web dir
        file_path = os.path.join(WEB_DIR, path.lstrip("/"))

    # Security: prevent path traversal
    file_path = os.path.realpath(file_path)
    allowed_dirs = [os.path.realpath(d) for d in [WEB_DIR, BGM_DIR, EXPR_DIR]]
    if not any(file_path.startswith(d) for d in allowed_dirs):
        await send_response(writer, 403, b"Forbidden")
        return

    if not os.path.isfile(file_path):
        await send_response(writer, 404, b"Not Found")
        return

    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"

    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except Exception:
        await send_response(writer, 500, b"Read Error")
        return

    await send_response(writer, 200, data, content_type=content_type, extra_headers=cors_headers())


def cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


async def send_json(writer: asyncio.StreamWriter, status: int, data: dict):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    await send_response(writer, status, body, content_type="application/json", extra_headers=cors_headers())


async def send_response(
    writer: asyncio.StreamWriter,
    status: int,
    body: bytes,
    content_type: str = "text/plain",
    extra_headers: dict | None = None,
):
    reason = HTTPStatus(status).phrase
    header = f"HTTP/1.1 {status} {reason}\r\n"
    header += f"Content-Type: {content_type}\r\n"
    header += f"Content-Length: {len(body)}\r\n"
    if extra_headers:
        for k, v in extra_headers.items():
            header += f"{k}: {v}\r\n"
    header += "\r\n"

    writer.write(header.encode("utf-8") + body)
    await writer.drain()


# ========== Main ==========

async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", PORT)
    log.info(f"听泉直播间桥接服务已启动: http://localhost:{PORT}")
    log.info(f"  POST /send    <- Claude Code 发消息")
    log.info(f"  GET  /events  -> 浏览器 SSE 接收")
    log.info(f"  GET  /        -> 直播间页面")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("桥接服务已关闭")
