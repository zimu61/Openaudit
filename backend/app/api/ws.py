import uuid
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as redis

from app.core.config import settings

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, scan_id: str, websocket: WebSocket):
        await websocket.accept()
        if scan_id not in self.active_connections:
            self.active_connections[scan_id] = []
        self.active_connections[scan_id].append(websocket)

    def disconnect(self, scan_id: str, websocket: WebSocket):
        if scan_id in self.active_connections:
            self.active_connections[scan_id].remove(websocket)
            if not self.active_connections[scan_id]:
                del self.active_connections[scan_id]

    async def send_progress(self, scan_id: str, data: dict):
        if scan_id in self.active_connections:
            message = json.dumps(data)
            for connection in self.active_connections[scan_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    pass


manager = ConnectionManager()


@router.websocket("/ws/scans/{scan_id}")
async def scan_progress_ws(websocket: WebSocket, scan_id: uuid.UUID):
    scan_id_str = str(scan_id)
    await manager.connect(scan_id_str, websocket)

    # Subscribe to Redis pub/sub for this scan
    r = redis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    channel = f"scan_progress:{scan_id_str}"
    await pubsub.subscribe(channel)

    try:
        # Listen for messages from Redis and forward to WebSocket
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
                if data.get("status") in ("completed", "failed"):
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await r.close()
        manager.disconnect(scan_id_str, websocket)
