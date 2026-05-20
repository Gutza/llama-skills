"""Pure registry formatting and message injection (no I/O)."""

from .models import SkillEntry

_REGISTRY_HEADER = """## Available Skills

You have access to the following skills. When the user's request matches a skill's purpose, use MCP `get_skill` with the skill name to load its full instructions before proceeding.
"""


def build_registry_block(entries: list[SkillEntry]) -> str:
    """Build the skills registry block for injection into the system prompt."""
    if not entries:
        return ""

    lines = [_REGISTRY_HEADER.rstrip(), ""]
    for entry in entries:
        line = f"- **{entry.name}**: {entry.description}"
        if entry.when_to_use:
            line = f"{line} [{entry.when_to_use}]"
        lines.append(line)
    return "\n".join(lines)


def inject_registry(messages: list, registry: str) -> list:
    """Prepend registry to the first system message or insert a new one."""
    if not registry.strip():
        return list(messages)

    updated = [dict(message) for message in messages]
    for index, message in enumerate(updated):
        if message.get("role") != "system":
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            original = "\n".join(text_parts)
        else:
            original = str(content) if content is not None else ""

        if original.strip():
            message["content"] = f"{registry}\n\n{original}"
        else:
            message["content"] = registry
        return updated

    updated.insert(0, {"role": "system", "content": registry})
    return updated
