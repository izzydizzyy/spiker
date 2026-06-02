"""
Run this alongside main.py:
    python web/server.py

Or add asyncio.create_task(start_web()) to bot's setup_hook.
Listens on port 8080. Serve behind nginx/Cloudflare on your EC2.
"""

import asyncio
import json
import os
import sys
import logging
import websockets
from pathlib import Path

# Allow importing from parent
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import get_leaderboard, init_db
from cogs.leaderboard import ws_clients

log = logging.getLogger("web")
HOST = "0.0.0.0"
PORT = 8080
HTML_PATH = Path(__file__).parent / "index.html"


async def handler(websocket):
    ws_clients.add(websocket)
    log.info(f"WS client connected: {websocket.remote_address}")
    try:
        # Send current leaderboard immediately on connect
        rows = await get_leaderboard(limit=25)
        payload = json.dumps([
            {"rank": i + 1, "username": r["username"], "msgs": r["msgs"]}
            for i, r in enumerate(rows)
        ])
        await websocket.send(payload)
        # Keep connection alive
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        log.info(f"WS client disconnected")


async def serve_http(reader, writer):
    """Minimal HTTP server to serve index.html on the same port is tricky;
    use a separate port or nginx. This handles plain HTTP GET for the HTML."""
    try:
        request = await reader.read(1024)
        html = HTML_PATH.read_bytes()
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"Connection: close\r\n\r\n"
        ) + html
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def start_web():
    await init_db()
    # HTTP on 8080, WebSocket on 8081
    http_server = await asyncio.start_server(serve_http, HOST, 8080)
    ws_server = await websockets.serve(handler, HOST, 8081)
    log.info(f"HTTP leaderboard on :{8080}, WebSocket on :{8081}")
    await asyncio.gather(http_server.serve_forever(), ws_server.wait_closed())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_web())