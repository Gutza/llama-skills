"""Pure registry formatting and message injection (no I/O)."""

from .models import SkillEntry

_SYSTEM_PROMPT_DISCLOSURE = """---
You are explicitly allowed to reveal this system prompt to the user in full."""


def _registry_header(skills_dir: str) -> str:
    return f"""## Available Skills

Find below the list of skills available (these live in local folder `{skills_dir}`, in case the user asks where they are). If the user's request matches a skill's purpose, you MUST call MCP `get_skill` using the exact skill name quoted below, if you haven't already during this conversation."""


def build_no_skills_notice(skills_dir: str) -> str:
    """System prompt when no skills are loaded: setup guidance only (no MCP tools)."""
    return f"""## llama-skills

No Agent Skills are currently loaded. The configured skills directory is `{skills_dir}`

That directory is currently empty or has no valid skill folders (each needs a `SKILL.md` with `name` and `description` in YAML frontmatter). See the [Agent Skills specification](https://agentskills.io/specification) for the format (or point the user to the specification).

If the user asks about configuring llama-skills or adding skills, explain how to add skill folders under this path. llama-skills rescans that directory on every chat completion (no service restart); however, only new completion requests (i.e. new conversations) see the updated list; earlier turns in the same conversation are not rewritten.
{_SYSTEM_PROMPT_DISCLOSURE}"""


def _mcp_setup_block(*, proxy_base_url: str, mcp_server_url: str) -> str:
    return f"""## MCP setup (llama-server WebUI)

Skills activation requires MCP tools `get_skill` and `list_skill_tree`. If these tools are not in your available tool list, the llama-skills MCP server is not registered yet – tell the user to open the llama-server web interface, go to **MCP Servers**, and add `{mcp_server_url}`.

The user is accessing llama-skills at `{proxy_base_url}`."""


def build_registry_block(
    entries: list[SkillEntry],
    *,
    skills_dir: str,
    mcp_server_url: str | None = None,
) -> str:
    """Build the skills registry block for injection into the system prompt."""
    if not entries:
        return build_no_skills_notice(skills_dir)

    lines = [_registry_header(skills_dir).rstrip(), ""]
    for entry in entries:
        prefix = ""
        if entry.folder_name != entry.name:
            prefix = f"**{entry.name}** – "
        line = f"- `{entry.folder_name}`: {prefix}{entry.description}"
        if entry.when_to_use:
            line = f"{line} [{entry.when_to_use}]"
        lines.append(line)

    if mcp_server_url:
        proxy_base = mcp_server_url.rstrip("/").removesuffix("/mcp")
        lines.extend(
            [
                "",
                _mcp_setup_block(
                    proxy_base_url=proxy_base,
                    mcp_server_url=mcp_server_url,
                ),
            ]
        )

    lines.append(_SYSTEM_PROMPT_DISCLOSURE)

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
