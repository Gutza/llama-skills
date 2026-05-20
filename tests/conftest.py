"""Shared pytest fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from skills_proxy.config import Settings
from skills_proxy.main import create_app
from skills_proxy.models import SkillEntry, SkillFileNotFound, SkillNotFound
from skills_proxy.skill_store import FilesystemSkillStore

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "skills"


@pytest.fixture
def skills_dir(tmp_path):
    """Copy fixture skills into a temporary directory."""
    target = tmp_path / "skills"
    target.mkdir()
    for child in FIXTURES_DIR.iterdir():
        if not child.is_dir():
            continue
        dest = target / child.name
        for path in child.rglob("*"):
            if path.is_file():
                rel = path.relative_to(child)
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture
def settings(skills_dir):
    return Settings(
        skills_dir=str(skills_dir),
        backend="http://llama-backend.test",
        host="127.0.0.1",
        port=18081,
    )


@pytest.fixture
def store(settings):
    return FilesystemSkillStore(settings)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@dataclass
class FakeSkillStore:
    """In-memory SkillStore for proxy unit tests."""

    entries: list[SkillEntry]
    files: dict[tuple[str, str], str]
    trees: dict[str, str]

    def list_registry_entries(self) -> list[SkillEntry]:
        return list(self.entries)

    def read_file(
        self, name: str, path: str = "SKILL.md", trim_frontmatter: bool = False
    ) -> str:
        key = (name, path)
        if key not in self.files:
            raise SkillFileNotFound(path)
        return self.files[key]

    def list_tree(self, name: str) -> str:
        if name not in self.trees:
            raise SkillNotFound(name)
        return self.trees[name]


@pytest.fixture
def fake_store():
    return FakeSkillStore(
        entries=[
            SkillEntry(folder_name="alpha", name="alpha", description="First skill"),
            SkillEntry(
                folder_name="beta",
                name="beta",
                description="Second skill",
                when_to_use="For beta tasks",
            ),
        ],
        files={("alpha", "SKILL.md"): "# Alpha"},
        trees={"alpha": "SKILL.md"},
    )


@pytest.fixture
def proxy_client(settings, fake_store):
    with TestClient(create_app(settings, store=fake_store)) as test_client:
        yield test_client
