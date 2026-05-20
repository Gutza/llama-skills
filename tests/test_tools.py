"""GET/POST /tools integration tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx


def test_list_tools_includes_skill_tools(client):
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    ids = {t["tool"] for t in tools}
    assert "get_skill" in ids
    assert "list_skill_tree" in ids
    get_skill = next(t for t in tools if t["tool"] == "get_skill")
    assert get_skill["type"] == "builtin"
    assert get_skill["definition"]["function"]["name"] == "get_skill"


def test_list_tools_merges_backend(client):
    backend_tools = [
        {
            "tool": "read_file",
            "display_name": "Read file",
            "type": "builtin",
            "permissions": {},
            "definition": {"type": "function", "function": {"name": "read_file"}},
        }
    ]

    async def mock_get(self, url, **kwargs):
        class MockResponse:
            status_code = 200

            def json(self):
                return backend_tools

        return MockResponse()

    with patch.object(httpx.AsyncClient, "get", mock_get):
        response = client.get("/tools")

    tools = response.json()
    ids = {t["tool"] for t in tools}
    assert "read_file" in ids
    assert "get_skill" in ids


def test_get_skill_returns_content(client):
    response = client.post(
        "/tools",
        json={"tool": "get_skill", "params": {"name": "demo-skill"}},
    )
    assert response.status_code == 200
    payload = response.json()
    text = payload["plain_text_response"]
    assert "Demo Skill" in text
    assert "name: demo-skill" not in text
    assert not text.startswith("---")


def test_get_skill_overview_omits_frontmatter(client):
    response = client.post(
        "/tools",
        json={"tool": "get_skill", "params": {"name": "demo-skill", "path": ""}},
    )
    text = response.json()["plain_text_response"]
    assert "# Demo Skill" in text
    assert "name: demo-skill" not in text
    assert not text.startswith("---")


def test_get_skill_explicit_skill_md_includes_frontmatter(client):
    response = client.post(
        "/tools",
        json={
            "tool": "get_skill",
            "params": {"name": "demo-skill", "path": "SKILL.md"},
        },
    )
    text = response.json()["plain_text_response"]
    assert text.startswith("---")
    assert "name: demo-skill" in text


def test_get_skill_not_found(client):
    response = client.post(
        "/tools",
        json={"tool": "get_skill", "params": {"name": "missing"}},
    )
    payload = response.json()
    assert payload["error"] == "skill 'missing' not found"


def test_get_skill_invalid_path(client):
    response = client.post(
        "/tools",
        json={
            "tool": "get_skill",
            "params": {"name": "demo-skill", "path": "../../../etc/passwd"},
        },
    )
    payload = response.json()
    assert payload["error"] == "invalid path"


def test_list_skill_tree(client):
    response = client.post(
        "/tools",
        json={"tool": "list_skill_tree", "params": {"name": "demo-skill"}},
    )
    text = response.json()["plain_text_response"]
    assert "SKILL.md" in text
    assert "references/REFERENCE.md" in text


def test_invoke_forwards_unknown_tool_to_backend(client):
    captured: dict = {}

    async def mock_post(self, url, **kwargs):
        captured["url"] = url
        captured["content"] = kwargs.get("content")

        class MockResponse:
            status_code = 200
            content = json.dumps({"plain_text_response": "ok"}).encode()
            headers = {"content-type": "application/json"}

        return MockResponse()

    with patch.object(httpx.AsyncClient, "post", mock_post):
        response = client.post(
            "/tools",
            json={"tool": "read_file", "params": {"path": "/tmp/x"}},
        )

    assert response.status_code == 200
    assert captured["url"] == "/tools"
    assert b"read_file" in captured["content"]
