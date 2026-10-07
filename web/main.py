import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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


def create_app() -> FastAPI:
    application = FastAPI(
        title="Bulevar del Café",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    application.include_router(router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
