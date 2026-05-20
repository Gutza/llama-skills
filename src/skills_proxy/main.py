"""Composition root: Starlette app, routes, lifespan, and CLI entry point."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route

from .config import Settings
from .proxy import chat_completions, passthrough
from .skill_store import FilesystemSkillStore, SkillStore
from .tools_handler import invoke_tool, list_tools
from .version import __version__

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings,
    *,
    store: SkillStore | None = None,
) -> Starlette:
    """Wire dependencies and return the ASGI application."""
    if store is None:
        store = FilesystemSkillStore(settings)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        logger.info(
            "llama-skills %s starting (backend %s, skills_dir %s)",
            __version__,
            settings.backend,
            settings.skills_dir,
        )
        app.state.skill_store = store
        app.state.settings = settings
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=settings.backend,
                    timeout=httpx.Timeout(None),
                )
            )
            app.state.http_client = client
            yield

    routes = [
        Route("/tools", list_tools, methods=["GET"]),
        Route("/tools", invoke_tool, methods=["POST"]),
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/{path:path}", passthrough),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)
    return CORSMiddleware(
        app,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def run() -> None:
    """Load settings from the environment and start uvicorn."""
    settings = Settings.from_env()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
