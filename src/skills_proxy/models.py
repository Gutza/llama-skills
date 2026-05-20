"""Domain types and exceptions for llama-skills."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillEntry:
    """A skill listed in the injected registry block."""

    folder_name: str  # Folder name under LLAMA_SKILLS_DIR; `get_skill` `name` argument
    name: str  # YAML `name` field in SKILL.md
    description: str  # YAML `description` field in SKILL.md
    when_to_use: str | None = None  # YAML `when_to_use` field in SKILL.md


class SkillNotFound(Exception):
    """Raised when a skill folder does not exist."""


class InvalidPath(Exception):
    """Raised when a path resolves outside the skill folder."""


class SkillFileNotFound(Exception):
    """Raised when a file within a skill folder does not exist."""
