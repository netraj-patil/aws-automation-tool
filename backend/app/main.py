"""FastAPI application entry point for the AWS automation agent."""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes.agent_routes import router
from app.services.session_store import session_store
from app.utils.logging_decorator import get_logger


load_dotenv()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize application services and log lifecycle events."""
    load_dotenv()
    logger.info(
        "AWS Automation Agent starting",
        extra={"session_store_backend": session_store.backend},
    )
    yield


app = FastAPI(
    title="AWS Automation Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app_env = os.getenv("APP_ENV", "development").lower()
if app_env == "production":
    allowed_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(HTTPException)
async def agent_http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Emit declared agent errors without FastAPI's default detail wrapper."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=exc.headers,
        )
    return await http_exception_handler(request, exc)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a lightweight service health response."""
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
