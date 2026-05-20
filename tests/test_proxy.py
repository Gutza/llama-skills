"""Proxy handler tests with fake store and mocked backend."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx


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
    assert "**alpha**" in system["content"]
    assert "**beta**" in system["content"]
    assert "[For beta tasks]" in system["content"]


def test_passthrough_forwards_unchanged(proxy_client):
    captured: dict = {}

    async def mock_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
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
    assert captured["url"] == "http://llama-backend.test/v1/models"
    assert captured["body"] in (None, b"")


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
