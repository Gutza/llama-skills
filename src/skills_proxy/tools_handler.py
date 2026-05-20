"""llama-server /tools API for skill activation (WebUI-native)."""

from __future__ import annotations

import json
import logging

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .models import InvalidPath, SkillFileNotFound, SkillNotFound
from .skill_store import SkillStore

logger = logging.getLogger(__name__)

_GET_SKILL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_skill",
        "description": (
            "Retrieve an overview of the skill if no path is provided, or the "
            "content of the specific file indicated by the path. Paths are "
            "relative to the skill folder."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill folder name (direct child of the skills directory).",
                },
                "path": {
                    "type": "string",
                    "description": "Relative path within the skill folder. Defaults to SKILL.md.",
                },
            },
            "required": ["name"],
        },
    },
}

_LIST_SKILL_TREE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_skill_tree",
        "description": (
            "Return the file and directory structure of a skill folder. "
            "Only use this tool as a last resort."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill folder name.",
                },
            },
            "required": ["name"],
        },
    },
}

SKILL_TOOLS: list[dict] = [
    {
        "tool": "get_skill",
        "display_name": "Get skill",
        "type": "builtin",
        "permissions": {},
        "definition": _GET_SKILL_DEFINITION,
    },
    {
        "tool": "list_skill_tree",
        "display_name": "List skill tree",
        "type": "builtin",
        "permissions": {},
        "definition": _LIST_SKILL_TREE_DEFINITION,
    },
]


def _merge_tool_lists(backend_tools: list, skill_tools: list[dict]) -> list:
    """Append skill tools; skill ids override backend entries on conflict."""
    by_id = {
        item["tool"]: item
        for item in backend_tools
        if isinstance(item, dict) and item.get("tool")
    }
    for tool in skill_tools:
        by_id[tool["tool"]] = tool
    return list(by_id.values())


async def list_tools(request: Request) -> JSONResponse:
    """GET /tools: skill tools merged with llama-server built-in tools when available."""
    client: httpx.AsyncClient = request.app.state.http_client
    tools: list = list(SKILL_TOOLS)

    try:
        response = await client.get("/tools")
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, list):
                tools = _merge_tool_lists(payload, SKILL_TOOLS)
        else:
            logger.warning(
                "llama-server GET /tools returned %s; serving skill tools only",
                response.status_code,
            )
    except httpx.RequestError as exc:
        logger.warning(
            "llama-server GET /tools failed: %s; serving skill tools only", exc
        )

    return JSONResponse(tools)


def _invoke_get_skill(store: SkillStore, params: dict) -> dict:
    name = params.get("name")
    if not name or not isinstance(name, str):
        return {"error": "missing required parameter: name"}

    path = params.get("path")
    trim_frontmatter = False
    if path is None or (isinstance(path, str) and path.strip() == ""):
        path = "SKILL.md"
        trim_frontmatter = True
    elif isinstance(path, str):
        path = path.strip()
    else:
        return {"error": "invalid path"}

    try:
        text = store.read_file(name, path, trim_frontmatter)
    except SkillNotFound:
        return {"error": f"skill '{name}' not found"}
    except InvalidPath:
        return {"error": "invalid path"}
    except SkillFileNotFound as exc:
        return {"error": f"file not found: {exc.args[0]}"}

    return {"plain_text_response": text}


def _invoke_list_skill_tree(store: SkillStore, params: dict) -> dict:
    name = params.get("name")
    if not name or not isinstance(name, str):
        return {"error": "missing required parameter: name"}

    try:
        text = store.list_tree(name)
    except SkillNotFound:
        return {"error": f"skill '{name}' not found"}

    return {"plain_text_response": text}


async def invoke_tool(request: Request) -> Response:
    """POST /tools: run skill tools locally; forward other tools to llama-server."""
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Response(content=body, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"error": "invalid request body"}, status_code=400)

    tool_id = payload.get("tool")
    if not tool_id or not isinstance(tool_id, str):
        return JSONResponse({"error": "missing required field: tool"}, status_code=400)

    params = payload.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return JSONResponse({"error": "params must be an object"}, status_code=400)

    store: SkillStore = request.app.state.skill_store

    if tool_id == "get_skill":
        return JSONResponse(_invoke_get_skill(store, params))
    if tool_id == "list_skill_tree":
        return JSONResponse(_invoke_list_skill_tree(store, params))

    client: httpx.AsyncClient = request.app.state.http_client
    try:
        response = await client.post(
            "/tools", content=body, headers={"content-type": "application/json"}
        )
    except httpx.RequestError as exc:
        logger.warning("llama-server POST /tools failed: %s", exc)
        return Response(
            "llama-server unreachable",
            status_code=502,
            media_type="text/plain",
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )
