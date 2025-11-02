from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello from backend!"}

import os
import asyncio
import time
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from backend.api.routes import router
from backend.services.logger import log_manager

# Configure logging
_LOG_LEVEL = os.getenv("FORGEX_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_name).setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
logger = logging.getLogger("forgex")

app = FastAPI(title="ForgeX Backend", version="1.0.0")

# Allow local dev from Vite/Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        dur_ms = (time.time() - start) * 1000
        logging.getLogger("forgex.http").info(f"{request.method} {request.url.path} -> {response.status_code} q={dict(request.query_params)} took={dur_ms:.1f}ms")
        return response
    except Exception as e:
        logging.getLogger("forgex.http").exception(f"Unhandled error for {request.method} {request.url.path}: {e}")
        raise

app.include_router(router)


@app.websocket("/ws/builds")
async def ws_builds(ws: WebSocket):
    await ws.accept()
    subscribed_build_id = None
    try:
        # Expect a subscribe message first
        msg = await ws.receive_json()
        if isinstance(msg, dict) and msg.get("type") == "subscribe":
            subscribed_build_id = msg.get("build_id")
            if not subscribed_build_id:
                await ws.send_json({"error": "build_id required"})
                await ws.close()
                return
            await log_manager.subscribe(subscribed_build_id, ws)
            logging.getLogger("forgex.ws").debug(f"WS subscribed to build {subscribed_build_id}")
            # Confirm subscription
            await ws.send_json({"type": "subscribed", "build_id": subscribed_build_id})
        else:
            await ws.send_json({"error": "first message must be subscribe"})
            await ws.close()
            return

        # Keep-alive ping/pong loop
        while True:
            try:
                # If client sends anything else, ignore but keep connection
                if ws.client_state == WebSocketState.CONNECTED:
                    await asyncio.sleep(15)
                    await ws.send_json({"type": "ping"})
                else:
                    break
            except Exception as ex:
                logging.getLogger("forgex.ws").debug(f"WS loop exception: {ex}")
                break

    except WebSocketDisconnect:
        logging.getLogger("forgex.ws").debug("WS disconnect")
    finally:
        if subscribed_build_id:
            await log_manager.unsubscribe(subscribed_build_id, ws)
            logging.getLogger("forgex.ws").debug(f"WS unsubscribed from build {subscribed_build_id}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FORGEX_BACKEND_PORT", "45555"))
    host = os.getenv("FORGEX_BACKEND_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, reload=False)
