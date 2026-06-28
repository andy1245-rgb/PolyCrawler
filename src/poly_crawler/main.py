"""Application lifecycle — FastAPI app factory, startup, and shutdown."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from poly_crawler.config import load_config
from poly_crawler.db import close_engine, init_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan — initialise engine on start, dispose on shutdown."""
    config = load_config()
    init_engine(config)
    yield
    await close_engine()


app = FastAPI(
    title="PolyCrawler",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
