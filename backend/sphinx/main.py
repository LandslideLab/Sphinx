import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sphinx.api import capture, policies, requests, ws
from sphinx.config import settings
from sphinx.core import policy_engine
from sphinx.core.events import set_event_loop
from sphinx.db import init_db

logging.basicConfig(level=logging.getLevelName(settings.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_event_loop(asyncio.get_running_loop())
    init_db()
    from sphinx.seed import seed_policies

    if settings.default_policy_seed:
        from sphinx.db import SessionLocal

        with SessionLocal() as db:
            seed_policies(db)
    if settings.seed_demo_data:
        from sphinx.seed import seed_capture, seed_demo

        with SessionLocal() as db:
            seed_demo(db)
            seed_capture(db)
    policy_engine.start()
    yield
    policy_engine.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Sphinx HITL Control Plane", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {"service": "sphinx", "status": "ok"}

    app.include_router(requests.router)
    app.include_router(policies.router)
    app.include_router(capture.router)
    app.add_api_websocket_route("/api/ws", ws.ws_endpoint)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("sphinx.main:app", host="0.0.0.0", port=settings.api_port, reload=False)


if __name__ == "__main__":
    main()
