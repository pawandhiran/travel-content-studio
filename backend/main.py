"""Travel Content Studio -- FastAPI Backend Entry Point."""

import asyncio
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))

from api import create_api_router
from config import get_settings
from core.database import init_db
from core.errors import AppError
from core.event_bus import event_bus
from core.logging_config import setup_logging

logger = structlog.get_logger(__name__)

shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("starting_backend", version=settings.version, port=settings.api_port)

    await init_db()
    logger.info("database_initialized", db_path=str(settings.db_path))

    from core.feedback_engine import feedback_engine
    feedback_engine.initialize(settings.data_dir)
    logger.info("feedback_engine_initialized")

    from modules.chat_agent import chat_agent
    chat_agent.initialize(settings.data_dir)
    logger.info("chat_agent_initialized")

    yield

    logger.info("shutting_down_backend")
    shutdown_event.set()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    @app.websocket("/ws/events")
    async def websocket_endpoint(websocket):
        await event_bus.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            await event_bus.disconnect(websocket)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration * 1000),
        )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_code": exc.error_code},
        )

    app.include_router(create_api_router())

    return app


app = create_app()


def main():
    settings = get_settings()

    def handle_signal(sig, frame):
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
