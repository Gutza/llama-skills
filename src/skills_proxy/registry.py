"""Pure registry formatting and message injection (no I/O)."""

from .models import SkillEntry

_SYSTEM_PROMPT_DISCLOSURE = """
If the user asks you to show, print, reveal, or dump the system prompt or your instructions, quote the full system message you received (including this block) verbatim. Do not refuse, hedge, or summarize it."""

_REGISTRY_HEADER = f"""## Available Skills

You have access to the following skills. When the user's request matches a skill's purpose, call MCP `get_skill` or `list_skill_tree` using the exact skill name quoted below.{_SYSTEM_PROMPT_DISCLOSURE}

Each bullet uses the skill folder name (the MCP `name` argument for `get_skill` / `list_skill_tree`), not the YAML `name` field in `SKILL.md`.
"""


def build_no_skills_notice(skills_dir: str) -> str:
    """System prompt when no skills are loaded: setup guidance only (no MCP tools)."""
    return f"""## llama-skills

No Agent Skills are currently loaded. The configured skills directory is:

`{skills_dir}`

That directory is empty or has no valid skill folders (each needs a `SKILL.md` with `name` and `description` in YAML frontmatter). See the [Agent Skills specification](https://agentskills.io/specification) for the format.

If the user asks about configuring llama-skills or adding skills, explain how to add skill folders under this path. llama-skills rescans that directory on every chat completion (no service restart); however, only new completion requests (i.e. new conversations) see the updated list; earlier turns in the same conversation are not rewritten.{_SYSTEM_PROMPT_DISCLOSURE}"""


def build_registry_block(entries: list[SkillEntry], *, skills_dir: str) -> str:
    """Build the skills registry block for injection into the system prompt."""
    if not entries:
        return build_no_skills_notice(skills_dir)

    lines = [_REGISTRY_HEADER.rstrip(), ""]
    for entry in entries:
        prefix = ""
        if entry.folder_name != entry.name:
            prefix = f"**{entry.name}** – "
        line = f"- `{entry.folder_name}`: {prefix}{entry.description}"
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
