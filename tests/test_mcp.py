"""MCP tool integration tests."""

from __future__ import annotations

import json

_MCP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}
_MCP_URL = "/mcp/"


def test_get_skill_returns_content(client):
    response = client.post(
        _MCP_URL,
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_skill",
                "arguments": {"name": "demo-skill"},
            },
        },
    )
    assert response.status_code == 200
    payload = _parse_json_response(response)
    text = _tool_text(payload)
    assert "Demo Skill" in text
    assert "name: demo-skill" not in text
    assert not text.startswith("---")


def test_get_skill_overview_omits_frontmatter(client):
    response = client.post(
        _MCP_URL,
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "get_skill",
                "arguments": {"name": "demo-skill", "path": ""},
            },
        },
    )
    payload = _parse_json_response(response)
    text = _tool_text(payload)
    assert "# Demo Skill" in text
    assert "name: demo-skill" not in text
    assert not text.startswith("---")


def test_get_skill_explicit_skill_md_includes_frontmatter(client):
    response = client.post(
        _MCP_URL,
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "get_skill",
                "arguments": {"name": "demo-skill", "path": "SKILL.md"},
            },
        },
    )
    payload = _parse_json_response(response)
    text = _tool_text(payload)
    assert text.startswith("---")
    assert "name: demo-skill" in text


def test_get_skill_not_found(client):
    response = client.post(
        _MCP_URL,
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_skill",
                "arguments": {"name": "missing"},
            },
        },
    )
    payload = _parse_json_response(response)
    assert _tool_is_error(payload)
    assert "skill 'missing' not found" in _error_text(payload)


def test_get_skill_invalid_path(client):
    response = client.post(
        _MCP_URL,
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_skill",
                "arguments": {"name": "demo-skill", "path": "../../../etc/passwd"},
            },
        },
    )
    payload = _parse_json_response(response)
    assert _tool_is_error(payload)
    assert "invalid path" in _error_text(payload)


def test_list_skill_tree(client):
    response = client.post(
        _MCP_URL,
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "list_skill_tree",
                "arguments": {"name": "demo-skill"},
            },
        },
    )
    payload = _parse_json_response(response)
    text = _tool_text(payload)
    assert "SKILL.md" in text
    assert "references/REFERENCE.md" in text


def _parse_json_response(response) -> dict:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    text = response.text.strip()
    if text.startswith("data:"):
        text = text.split("\n", 1)[-1].strip()
    return json.loads(text)


def _tool_text(payload: dict) -> str:
    result = payload.get("result", {})
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return content[0].get("text", "")
    structured = result.get("structuredContent", {})
    return str(structured.get("result", structured))


def _tool_is_error(payload: dict) -> bool:
    result = payload.get("result", {})
    return bool(result.get("isError"))


def _error_text(payload: dict) -> str:
    if payload.get("error"):
        return str(payload["error"].get("message", ""))
    result = payload.get("result", {})
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return content[0].get("text", "")
    return str(result)
