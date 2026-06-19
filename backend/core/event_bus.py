import json
from typing import Any

from fastapi import WebSocket

from .logging_config import get_logger

log = get_logger(__name__)


class EventBus:
    """Singleton WebSocket event bus for broadcasting real-time updates."""

    _instance: "EventBus | None" = None

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._clients: set[WebSocket] = set()
        return cls._instance

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        log.info("ws_client_connected", clients=self.client_count)

    async def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)
        log.info("ws_client_disconnected", clients=self.client_count)

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "data": data})
        disconnected: list[WebSocket] = []

        for client in self._clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            self._clients.discard(client)

    async def send_to(self, websocket: WebSocket, event_type: str, data: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "data": data})
        try:
            await websocket.send_text(message)
        except Exception:
            self._clients.discard(websocket)


event_bus = EventBus()
