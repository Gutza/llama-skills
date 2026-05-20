"""Unit tests for public base URL resolution."""

from starlette.requests import Request

from skills_proxy.config import Settings
from skills_proxy.proxy import resolve_public_base_url


def _request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
    }
    return Request(scope)


def test_resolve_public_base_url_uses_public_url_override():
    settings = Settings(
        skills_dir="/skills",
        backend="http://localhost:8080",
        host="0.0.0.0",
        port=8081,
        public_url="https://llm.example.com",
    )
    request = _request({"Host": "ignored.local:8081"})

    assert resolve_public_base_url(request, settings) == "https://llm.example.com"


def test_resolve_public_base_url_prefers_forwarded_host():
    settings = Settings(
        skills_dir="/skills",
        backend="http://localhost:8080",
        host="0.0.0.0",
        port=8081,
    )
    request = _request(
        {
            "Host": "internal:8081",
            "X-Forwarded-Host": "llm.example.com",
        }
    )

    assert resolve_public_base_url(request, settings) == "http://llm.example.com"


def test_resolve_public_base_url_uses_host_when_no_forwarded_host():
    settings = Settings(
        skills_dir="/skills",
        backend="http://localhost:8080",
        host="0.0.0.0",
        port=8081,
    )
    request = _request({"Host": "foo-server:8081"})

    assert resolve_public_base_url(request, settings) == "http://foo-server:8081"


def test_resolve_public_base_url_returns_none_without_host():
    settings = Settings(
        skills_dir="/skills",
        backend="http://localhost:8080",
        host="0.0.0.0",
        port=8081,
    )
    request = _request()

    assert resolve_public_base_url(request, settings) is None


def test_resolve_public_base_url_uses_forwarded_proto():
    settings = Settings(
        skills_dir="/skills",
        backend="http://localhost:8080",
        host="0.0.0.0",
        port=8081,
    )
    request = _request({"Host": "llm.example.com", "X-Forwarded-Proto": "https"})

    assert resolve_public_base_url(request, settings) == "https://llm.example.com"
