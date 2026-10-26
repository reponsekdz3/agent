import json
from typing import List, Dict, Any
from fastapi import WebSocket
from nova_apex.core.logger import agent_logger

class WebSocketManager:
    """
    Manages live WebSocket subscriptions for Mission Control UI clients.
    Transmits real-time thought streams, screenshots, terminal traces, and goal statuses.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Hook into agent logger
        agent_logger.register_listener(self.broadcast_sync)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def broadcast_sync(self, payload: Dict[str, Any]):
        # Broadcast safely to any active websocket loop
        import asyncio
        for conn in list(self.active_connections):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(conn.send_text(json.dumps(payload)))
            except Exception:
                pass

    async def broadcast(self, payload: Dict[str, Any]):
        msg = json.dumps(payload)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(msg)
            except Exception:
                self.disconnect(connection)

ws_manager = WebSocketManager()
