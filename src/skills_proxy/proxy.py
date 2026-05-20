"""HTTP proxy handlers with skill registry injection."""

from __future__ import annotations

import json

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from .registry import build_registry_block, inject_registry

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


async def _forward_request(
    client: httpx.AsyncClient,
    backend_url: str,
    request: Request,
    *,
    body: bytes,
    stream: bool,
) -> Response:
    url = f"{backend_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }

    if stream:
        return await _forward_streaming(client, request.method, url, headers, body)

    response = await client.request(
        request.method,
        url,
        headers=headers,
        content=body,
    )
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )


async def _forward_streaming(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
) -> StreamingResponse:
    request = client.build_request(method, url, headers=headers, content=body)
    send = await client.send(request, stream=True)

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
