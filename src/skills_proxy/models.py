"""Domain types and exceptions for llama-skills."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillEntry:
    """A skill listed in the injected registry block."""

    name: str
    description: str
    when_to_use: str | None = None


class SkillNotFound(Exception):
    """Raised when a skill folder does not exist."""


class InvalidPath(Exception):
    """Raised when a path resolves outside the skill folder."""


class SkillFileNotFound(Exception):
    """Raised when a file within a skill folder does not exist."""
