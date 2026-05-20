"""Skills directory access behind a SkillStore protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
import re

import yaml

from .config import Settings
from .models import InvalidPath, SkillEntry, SkillFileNotFound, SkillNotFound

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


class SkillStore(Protocol):
    """Protocol for skill directory access (filesystem or cached wrapper)."""

    def list_registry_entries(self) -> list[SkillEntry]: ...

    def read_file(self, name: str, path: str = "SKILL.md") -> str: ...

    def list_tree(self, name: str) -> str: ...


class FilesystemSkillStore:
    """Reads skills from a directory on every call (no caching in iteration 1)."""

    def __init__(self, settings: Settings) -> None:
        self._skills_dir = Path(settings.skills_dir).resolve()

    def list_registry_entries(self) -> list[SkillEntry]:
        if not self._skills_dir.is_dir():
            return []

        entries: list[SkillEntry] = []
        for child in sorted(self._skills_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            frontmatter = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            if frontmatter is None:
                continue
            name = frontmatter.get("name")
            if not name: # names are mandatory per the [Agent Skills specification](https://agentskills.io/specification)
                continue
            if _is_disabled(frontmatter):
                continue

            description = frontmatter.get("description")
            if not description:
                continue

            when_to_use = frontmatter.get("when_to_use")
            entries.append(
                SkillEntry(
                    folder_name=child.name,
                    name=str(name),
                    description=str(description),
                    when_to_use=str(when_to_use) if when_to_use else None,
                )
            )
        return entries

    def read_file(self, name: str, path: str = "SKILL.md") -> str:
        target = self._resolve_path(name, path)
        if not target.is_file():
            raise SkillFileNotFound(path)
        return target.read_text(encoding="utf-8")

    def list_tree(self, name: str) -> str:
        skill_root = self._resolve_path(name, ".")
        if not skill_root.is_dir():
            raise SkillNotFound(name)

        paths: list[str] = []
        for item in sorted(skill_root.rglob("*")):
            rel = item.relative_to(skill_root).as_posix()
            if item.is_dir():
                paths.append(f"{rel}/")
            else:
                paths.append(rel)
        return "\n".join(paths)

    def _resolve_path(self, name: str, rel_path: str) -> Path:
        skill_root = (self._skills_dir / name).resolve()
        if not skill_root.is_dir():
            raise SkillNotFound(name)

        if rel_path in (".", ""):
            return skill_root

        target = (skill_root / rel_path).resolve()
        if not target.is_relative_to(skill_root):
            raise InvalidPath(rel_path)
        if not target.exists():
            raise SkillFileNotFound(rel_path)
        return target


def _parse_frontmatter(text: str) -> dict | None:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        return None
    return data


def _is_disabled(frontmatter: dict) -> bool:
    value = frontmatter.get("disable-model-invocation")
    if value is True:
        return True
    if isinstance(value, str) and value.lower() == "true":
        return True
    return False
