import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.database import init_db
from web.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bulevar")
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
    except Exception:
        logger.exception("No se pudieron crear las tablas. Revisa DATABASE_URL.")
        raise
    yield


class HeadAsGetMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return
        request = dict(scope)
        request["method"] = "GET"

        async def send_without_body(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message["headers"]
                    if name.lower() not in {b"content-length", b"transfer-encoding"}
                ]
                headers.append((b"content-length", b"0"))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app(request, receive, send_without_body)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Bulevar del Café",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(HeadAsGetMiddleware)
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    application.include_router(router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
