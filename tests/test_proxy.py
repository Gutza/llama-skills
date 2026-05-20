"""Proxy handler tests with fake store and mocked backend."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx


def test_chat_completions_injects_mcp_url_from_host_header(proxy_client):
    captured: dict = {}

    async def mock_request(self, method, url, **kwargs):
        captured["body"] = json.loads(kwargs.get("content") or b"{}")

        class MockResponse:
            status_code = 200
            content = b"{}"
            headers = {"content-type": "application/json"}

        return MockResponse()

    with patch.object(httpx.AsyncClient, "request", mock_request):
        response = proxy_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hi"}]},
            headers={"Host": "foo-server:8081"},
        )

    assert response.status_code == 200
    system = next(m for m in captured["body"]["messages"] if m["role"] == "system")
    assert "http://foo-server:8081/mcp/" in system["content"]
    assert "## MCP setup (llama-server WebUI)" in system["content"]


def test_chat_completions_injects_https_mcp_url_with_forwarded_proto(proxy_client):
    captured: dict = {}

    async def mock_request(self, method, url, **kwargs):
        captured["body"] = json.loads(kwargs.get("content") or b"{}")

        class MockResponse:
            status_code = 200
            content = b"{}"
            headers = {"content-type": "application/json"}

        return MockResponse()

    with patch.object(httpx.AsyncClient, "request", mock_request):
        response = proxy_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hi"}]},
            headers={
                "Host": "foo-server:8081",
                "X-Forwarded-Proto": "https",
            },
        )

    assert response.status_code == 200
    system = next(m for m in captured["body"]["messages"] if m["role"] == "system")
    assert "https://foo-server:8081/mcp/" in system["content"]


def test_chat_completions_injects_registry(proxy_client):
    captured: dict = {}

    async def mock_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["body"] = json.loads(kwargs.get("content") or b"{}")

        class MockResponse:
            status_code = 200
            content = b"{}"
            headers = {"content-type": "application/json"}

        return MockResponse()

    with patch.object(httpx.AsyncClient, "request", mock_request):
        response = proxy_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hi"}], "model": "test"},
        )

    assert response.status_code == 200
    messages = captured["body"]["messages"]
    system = next(message for message in messages if message["role"] == "system")
    assert "## Available Skills" in system["content"]
    assert "`alpha`" in system["content"]
    assert "`beta`" in system["content"]
    assert "[For beta tasks]" in system["content"]


def test_passthrough_forwards_unchanged(proxy_client):
    captured: dict = {}

    async def mock_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers") or {}
        captured["body"] = kwargs.get("content")

        class MockResponse:
            status_code = 200
            content = b'{"models":[]}'
            headers = {"content-type": "application/json"}

        return MockResponse()

    with patch.object(httpx.AsyncClient, "request", mock_request):
        response = proxy_client.get("/v1/models")

    assert response.status_code == 200
    assert captured["method"] == "GET"
    assert captured["url"] == "/v1/models"
    assert captured["body"] in (None, b"")
    assert "host" not in {k.lower() for k in captured["headers"]}
    assert captured["headers"].get("x-forwarded-proto") == "http"


def test_cors_proxy_head_probe_returns_200_without_forwarding(proxy_client):
    with patch.object(httpx.AsyncClient, "request") as mock_request:
        response = proxy_client.head("/cors-proxy")
    mock_request.assert_not_called()
    assert response.status_code == 200


def test_cors_proxy_adds_scheme_to_url_query(proxy_client):
    captured: dict = {}

    async def mock_request(self, method, url, **kwargs):
        captured["url"] = url

        class MockResponse:
            status_code = 200
            content = b""
            headers = {}

        return MockResponse()

    with patch.object(httpx.AsyncClient, "request", mock_request):
        proxy_client.get(
            "/cors-proxy",
            params={"url": "foo-server:8081/mcp/"},
        )

    assert captured["url"] == "/cors-proxy?url=http%3A%2F%2Ffoo-server%3A8081%2Fmcp%2F"


def test_passthrough_returns_502_when_backend_unreachable(skills_dir):
    from starlette.testclient import TestClient

    from skills_proxy.config import Settings
    from skills_proxy.main import create_app

    settings = Settings(
        skills_dir=str(skills_dir),
        backend="http://127.0.0.1:1",
        host="127.0.0.1",
        port=18081,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 502
    assert "llama-server unreachable" in response.text


def test_chat_completions_streaming(proxy_client):
    captured: dict = {}

    class MockStream:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def aiter_bytes(self):
            yield b"data: {}\n\n"

        async def aclose(self):
            return None

    async def mock_send(self, request, **kwargs):
        captured["stream"] = kwargs.get("stream")

        class MockRequest:
            method = "POST"
            url = "/v1/chat/completions"

        return MockStream()

    def mock_build_request(self, method, url, **kwargs):
        captured["body"] = json.loads(kwargs.get("content") or b"{}")
        return object()

    with (
        patch.object(httpx.AsyncClient, "build_request", mock_build_request),
        patch.object(httpx.AsyncClient, "send", mock_send),
    ):
        response = proxy_client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    assert captured["stream"] is True
    assert "messages" in captured["body"]
