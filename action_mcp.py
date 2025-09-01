"""Minimal ActionMCP server that communicates with the Chrome extension.
It relays actions and chat messages using the protocol described in README_v2.md.
"""

import json
import logging
from typing import Any, Dict

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("action_mcp")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def send_chat(ws: WebSocket, message: str) -> None:
    await ws.send_text(json.dumps({"type": "chat", "message": message}))


async def handle_extension_message(ws: WebSocket, payload: Dict[str, Any]) -> None:
    msg_type = payload.get("type")
    logger.info("Received %s", msg_type)

    if msg_type == "LOAD_COMPLETE":
        await send_chat(ws, "페이지 로딩 완료")
        await ws.send_text(json.dumps({"type": "request_dom"}))

    elif msg_type in ("DOM_DATA", "dom_with_image"):
        dom = payload.get("dom", [])
        dom_len = len(dom) if isinstance(dom, list) else len(dom)
        img_len = len(payload.get("image", ""))
        if isinstance(dom, str) and "password" in dom.lower():
            await send_chat(ws, "로그인이 필요합니다. 로그인 후 '진행'을 눌러주세요.")
        else:
            await send_chat(ws, f"DOM 수신 ({dom_len} items, image {img_len} bytes)")

    elif msg_type == "ACTION_RESULT":
        result = payload.get("result", {})
        await send_chat(ws, f"액션 결과: {result}")

    elif msg_type == "chat":
        text = payload.get("message", "")
        if "로그인" in text:
            await send_chat(ws, "로그인을 진행해주세요.")
        else:
            await send_chat(ws, f"메시지 수신: {text}")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await send_chat(ws, "ActionMCP에 연결되었습니다")
    try:
        while True:
            data = await ws.receive_text()
            payload = json.loads(data)
            await handle_extension_message(ws, payload)
    except WebSocketDisconnect:
        logger.info("Extension disconnected")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
