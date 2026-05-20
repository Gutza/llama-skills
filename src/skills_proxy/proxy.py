"""HTTP proxy handlers with skill registry injection."""

from __future__ import annotations

import json
import logging

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from .registry import build_registry_block, inject_registry

logger = logging.getLogger(__name__)

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


async def chat_completions(request: Request) -> Response:
    """Inject skill registry into chat/completions and forward to llama-server."""
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Response(content=body, status_code=400)

    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    store = request.app.state.skill_store
    entries = store.list_registry_entries()
    registry = build_registry_block(entries)
    payload["messages"] = inject_registry(messages, registry)
    modified_body = json.dumps(payload).encode("utf-8")

    client: httpx.AsyncClient = request.app.state.http_client
    settings = request.app.state.settings
    return await _forward_request(
        client,
        settings.backend,
        request,
        body=modified_body,
        stream=bool(payload.get("stream")),
    )


async def passthrough(request: Request) -> Response:
    """Transparently forward all other requests to llama-server."""
    body = await request.body()
    client: httpx.AsyncClient = request.app.state.http_client
    settings = request.app.state.settings
    stream = False
    if request.method == "POST" and body:
        try:
            payload = json.loads(body)
            stream = bool(payload.get("stream"))
        except json.JSONDecodeError:
            stream = False

    return await _forward_request(
        client,
        settings.backend,
        request,
        body=body,
        stream=stream,
    )


def _backend_path(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


def _backend_unreachable_response(backend_url: str, exc: Exception) -> Response:
    logger.warning("llama-server unreachable at %s: %s", backend_url, exc)
    return Response(
        f"llama-server unreachable ({backend_url})",
        status_code=502,
        media_type="text/plain",
    )


async def _forward_request(
    client: httpx.AsyncClient,
    backend_url: str,
    request: Request,
    *,
    body: bytes,
    stream: bool,
) -> Response:
    path = _backend_path(request)
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }

    if stream:
        return await _forward_streaming(
            client, backend_url, request.method, path, headers, body
        )

    try:
        response = await client.request(
            request.method,
            path,
            headers=headers,
            content=body,
        )
    except httpx.RequestError as exc:
        return _backend_unreachable_response(backend_url, exc)

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )


async def _forward_streaming(
    client: httpx.AsyncClient,
    backend_url: str,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
) -> Response:
    httpx_request = client.build_request(method, path, headers=headers, content=body)
    try:
        send = await client.send(httpx_request, stream=True)
    except httpx.RequestError as exc:
        return _backend_unreachable_response(backend_url, exc)

    async def stream_body():
        try:
            async for chunk in send.aiter_bytes():
                yield chunk
        finally:
            await send.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=send.status_code,
        headers=dict(send.headers),
    )
