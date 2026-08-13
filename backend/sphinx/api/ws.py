from fastapi import WebSocket, WebSocketDisconnect

from sphinx.core.events import TOPIC_DECISIONS, TOPIC_POLICIES, TOPIC_REQUESTS, bus


async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    topics = [TOPIC_REQUESTS, TOPIC_DECISIONS, TOPIC_POLICIES]
    q = await bus.subscribe(topics)
    try:
        await websocket.send_json({"topic": "hello", "data": {"service": "sphinx"}})
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(topics, q)
