"""Unit tests for pure registry formatting and injection."""

from skills_proxy.models import SkillEntry
from skills_proxy.registry import build_registry_block, inject_registry


def test_build_registry_block_includes_header_and_entries():
    entries = [
        SkillEntry(name="alpha", description="First skill"),
        SkillEntry(
            name="beta",
            description="Second skill",
            when_to_use="For beta tasks",
        ),
    ]
    block = build_registry_block(entries)

    assert "## Available Skills" in block
    assert "get_skill" in block
    assert "- **alpha**: First skill" in block
    assert "- **beta**: Second skill [For beta tasks]" in block


def test_build_registry_block_empty_entries():
    assert build_registry_block([]) == ""


def test_inject_registry_skips_when_no_skills():
    messages = [{"role": "system", "content": "You are helpful."}]
    result = inject_registry(messages, build_registry_block([]))
    assert result == messages
    assert result is not messages


def test_inject_registry_prepends_existing_system_message():
    messages = [{"role": "system", "content": "You are helpful."}]
    registry = "## Available Skills\n\n- **x**: y"
    result = inject_registry(messages, registry)

    assert len(result) == 1
    assert result[0]["content"].startswith(registry)
    assert "You are helpful." in result[0]["content"]
    assert "\n\n" in result[0]["content"]


def test_inject_registry_inserts_system_message_when_missing():
    messages = [{"role": "user", "content": "Hello"}]
    registry = "## Available Skills"
    result = inject_registry(messages, registry)

    assert result[0]["role"] == "system"
    assert result[0]["content"] == registry
    assert result[1]["role"] == "user"


def test_inject_registry_empty_registry_returns_copy():
    messages = [{"role": "user", "content": "Hi"}]
    result = inject_registry(messages, "")
    assert result == messages
    assert result is not messages
