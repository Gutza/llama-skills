"""Filesystem skill store tests."""

import pytest

from skills_proxy.models import InvalidPath, SkillFileNotFound, SkillNotFound


def test_list_registry_entries_includes_demo_skill(store):
    entries = store.list_registry_entries()
    names = [entry.name for entry in entries]
    assert "demo-skill" in names
    assert "disabled-skill" not in names
    assert "incomplete-skill" not in names


def test_list_registry_entries_when_to_use(store):
    entries = store.list_registry_entries()
    demo = next(entry for entry in entries if entry.name == "demo-skill")
    assert demo.description == "A demo skill for testing"
    assert demo.when_to_use == "Use for demos"


def test_registry_uses_folder_name_for_mcp(store):
    mismatch = store._skills_dir / "folder-id"
    mismatch.mkdir()
    (mismatch / "SKILL.md").write_text(
        "---\nname: wrong-yaml-name\ndescription: Mismatched frontmatter name\n---\n",
        encoding="utf-8",
    )
    entries = store.list_registry_entries()
    entry = next(e for e in entries if e.folder_name == "folder-id")
    assert entry.description == "Mismatched frontmatter name"
    assert store.read_file("folder-id").startswith("---")


def test_hot_rescan_picks_up_new_skill(store, settings, tmp_path):
    new_skill = store._skills_dir / "fresh-skill"
    new_skill.mkdir()
    (new_skill / "SKILL.md").write_text(
        "---\nname: fresh-skill\ndescription: Newly added\n---\n",
        encoding="utf-8",
    )
    entries = store.list_registry_entries()
    assert any(entry.name == "fresh-skill" for entry in entries)


def test_read_file_default_skill_md(store):
    content = store.read_file("demo-skill")
    assert "Demo Skill" in content


def test_read_file_nested_path(store):
    content = store.read_file("demo-skill", "references/REFERENCE.md")
    assert "Reference content" in content


def test_read_file_skill_not_found(store):
    with pytest.raises(SkillNotFound):
        store.read_file("missing-skill")


def test_read_file_path_traversal(store):
    with pytest.raises(InvalidPath):
        store.read_file("demo-skill", "../disabled-skill/SKILL.md")


def test_read_file_missing_file(store):
    with pytest.raises(SkillFileNotFound):
        store.read_file("demo-skill", "missing.txt")


def test_list_tree(store):
    tree = store.list_tree("demo-skill")
    assert "SKILL.md" in tree
    assert "references/" in tree
    assert "references/REFERENCE.md" in tree


def test_list_tree_skill_not_found(store):
    with pytest.raises(SkillNotFound):
        store.list_tree("no-such-skill")


def test_disable_model_invocation_string(store, settings):
    disabled = store._skills_dir / "string-disabled"
    disabled.mkdir()
    (disabled / "SKILL.md").write_text(
        "---\nname: string-disabled\ndescription: Hidden\ndisable-model-invocation: 'true'\n---\n",
        encoding="utf-8",
    )
    names = [entry.name for entry in store.list_registry_entries()]
    assert "string-disabled" not in names
