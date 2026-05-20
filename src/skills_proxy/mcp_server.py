"""MCP Streamable HTTP server with skill activation tools."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from .config import Settings
from .models import InvalidPath, SkillFileNotFound, SkillNotFound
from .skill_store import SkillStore


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    """Configure MCP DNS rebinding checks from bind address."""
    if settings.host in ("0.0.0.0", "::"):
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "testserver",
            "localhost:*",
            "127.0.0.1:*",
            "[::1]:*",
            f"{settings.host}:*",
        ],
    )


def create_mcp_server(store: SkillStore, settings: Settings):
    """Create FastMCP instance and lifespan context manager for session manager."""
    mcp = FastMCP(
        "llama-skills",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=_transport_security(settings),
    )

    @mcp.tool()
    def get_skill(name: str, path: str | None = None) -> str:
        """Retrieve an overview of the skill if no path is provided, or the content of the specific file indicated by the path. Paths are relative to the skill folder."""
        if path is None or path.strip() == "":
            path = "SKILL.md"
        else:
            path = path.strip()
        try:
            return store.read_file(name, path)
        except SkillNotFound:
            raise ToolError(f"skill '{name}' not found") from None
        except InvalidPath:
            raise ToolError("invalid path") from None
        except SkillFileNotFound as exc:
            raise ToolError(f"file not found: {exc.args[0]}") from None

    @mcp.tool()
    def list_skill_tree(name: str) -> str:
        """Return the file and directory structure of a skill folder. Only use this tool as a last resort."""
        try:
            return store.list_tree(name)
        except SkillNotFound:
            raise ToolError(f"skill '{name}' not found") from None

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    return mcp, lifespan
