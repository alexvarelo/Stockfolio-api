import asyncio
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import yfinance as yf

from app.core.dependencies import get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_symbols(raw: str) -> List[str]:
    return list(dict.fromkeys(t.strip().upper() for t in raw.split(",") if t.strip()))


@router.websocket("/ws/prices")
async def stream_prices(websocket: WebSocket):
    """
    Stream real-time price updates over a WebSocket.

    Connect with:
        wss://<host>/api/v1/ws/prices?tickers=AAPL,MSFT&token=<jwt>

    Query params:
    - tickers: comma-separated list of symbols to subscribe to (required)
    - token: Supabase JWT, same token used as Bearer on the REST endpoints (required)

    Server messages:
        {"type": "subscribed", "tickers": [...]}
        {"type": "price", "data": {<raw yahoo streamer payload: id, price, change, changePercent, dayVolume, ...>}}
        {"type": "error", "detail": "..."}

    Client messages (optional, to change subscriptions on the fly):
        {"action": "subscribe", "tickers": ["NVDA"]}
        {"action": "unsubscribe", "tickers": ["AAPL"]}
    """
    token = websocket.query_params.get("token")
    symbols = _parse_symbols(websocket.query_params.get("tickers", ""))

    client = get_auth_service().get_current_client(token) if token else None
    if not client:
        await websocket.close(code=4401, reason="Invalid or missing token")
        return

    if not symbols:
        await websocket.close(code=4400, reason="tickers query param is required")
        return

    await websocket.accept()

    queue: asyncio.Queue = asyncio.Queue()

    def on_message(message: dict):
        queue.put_nowait(message)

    yf_ws = yf.AsyncWebSocket(verbose=False)

    async def forward_prices():
        while True:
            message = await queue.get()
            await websocket.send_json({"type": "price", "data": message})

    async def handle_client_messages():
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            tickers = _parse_symbols(",".join(data.get("tickers", [])))
            if not tickers:
                await websocket.send_json({"type": "error", "detail": "tickers list is required"})
                continue
            if action == "subscribe":
                await yf_ws.subscribe(tickers)
                await websocket.send_json({"type": "subscribed", "tickers": tickers})
            elif action == "unsubscribe":
                await yf_ws.unsubscribe(tickers)
                await websocket.send_json({"type": "unsubscribed", "tickers": tickers})
            else:
                await websocket.send_json({"type": "error", "detail": f"Unknown action: {action}"})

    listen_task = None
    tasks = []
    try:
        await yf_ws.subscribe(symbols)
        await websocket.send_json({"type": "subscribed", "tickers": symbols})

        listen_task = asyncio.create_task(yf_ws.listen(on_message))
        tasks = [
            asyncio.create_task(forward_prices()),
            asyncio.create_task(handle_client_messages()),
            listen_task,
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                logger.error(f"Price stream terminated with error: {exc}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error in price stream: {str(e)}", exc_info=True)
    finally:
        for task in tasks:
            task.cancel()
        try:
            await yf_ws.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
