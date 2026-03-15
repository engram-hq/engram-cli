"""Tests for the existing knowledge discovery module."""

import pytest

from engram_cli.discovery import (
    DiscoveredItem,
    ExistingKnowledge,
    discover_existing,
)


@pytest.fixture
def repo_with_skills(tmp_path):
    """Create a repo that has existing skills and memories."""
    # Source code
    (tmp_path / "README.md").write_text("# My Project\nA project with existing skills\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "myproject"\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n")

    # Existing skills (repo-level .skills dir)
    skills = tmp_path / ".skills"
    skills.mkdir()
    arch = skills / "architecture"
    arch.mkdir()
    (arch / "SKILL.md").write_text(
        "---\nname: myproject-architecture\n---\n\n# Architecture\n\n"
        "## Overview\nThis is a FastAPI app with PostgreSQL backend.\n\n"
        "## Key Design Decisions\n- FastAPI for async\n- SQLAlchemy ORM\n"
    )
    patterns = skills / "patterns"
    patterns.mkdir()
    (patterns / "SKILL.md").write_text(
        "---\nname: myproject-patterns\n---\n\n# Patterns\n\n"
        "## Code Organization\nSrc layout with services.\n"
    )

    # Existing memories
    memory = tmp_path / ".memory"
    memory.mkdir()
    sessions = memory / "sessions"
    sessions.mkdir()
    (sessions / "2026-01-15-myproject-overview.md").write_text(
        "---\ndate: 2026-01-15\ntype: exploration\n---\n\n"
        "# Session: myproject Deep Dive\n\n## Summary\nExplored the codebase.\n"
    )

    return tmp_path


@pytest.fixture
def repo_with_org_skills(tmp_path):
    """Create a repo alongside an org-skills repo."""
    # The repo itself
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "README.md").write_text("# My Repo\n")
    (repo / "main.py").write_text("print('hi')\n")

    # Sibling org-skills repo
    org_skills = tmp_path / "myorg-skills"
    org_skills.mkdir()
    org_knowledge = org_skills / "org-knowledge"
    org_knowledge.mkdir()
    (org_knowledge / "SKILL.md").write_text(
        "---\nname: org-stack\n---\n\n# Org Stack\nWe use Python + FastAPI.\n"
    )
    repo_dir = org_skills / "myrepo"
    repo_dir.mkdir()
    (repo_dir / "SKILL.md").write_text(
        "---\nname: myrepo-architecture\n---\n\n# Architecture\nService layer pattern.\n"
    )

    return repo


@pytest.fixture
def repo_with_engram_output(tmp_path):
    """Create a repo with previous engram-output."""
    repo = tmp_path / "webapp"
    repo.mkdir()
    (repo / "README.md").write_text("# WebApp\n")

    # Previous engram output alongside the repo
    output = tmp_path / "engram-output" / "webapp"
    output.mkdir(parents=True)
    skills = output / "skills" / "architecture"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: webapp-architecture\n---\n\n# Architecture\nNext.js SSR app.\n"
    )
    memories = output / "memories" / "sessions"
    memories.mkdir(parents=True)
    (memories / "2026-02-01-webapp-overview.md").write_text(
        "---\ndate: 2026-02-01\n---\n\n# Session: webapp overview\nSSR with React.\n"
    )

    return repo


@pytest.fixture
def empty_repo(tmp_path):
    """Create a repo with no existing knowledge."""
    (tmp_path / "README.md").write_text("# Fresh Repo\n")
    (tmp_path / "main.py").write_text("print('new')\n")
    return tmp_path


class TestDiscoverExisting:
    """Test the discovery function."""

    def test_discovers_repo_skills(self, repo_with_skills):
        result = discover_existing(repo_with_skills)
        assert result.has_existing
        assert len(result.skills) == 2  # architecture + patterns
        assert any("architecture" in s.path for s in result.skills)
        assert any("pattern" in s.path for s in result.skills)

    def test_discovers_repo_memories(self, repo_with_skills):
        result = discover_existing(repo_with_skills)
        assert len(result.memories) >= 1
        assert any("overview" in m.path for m in result.memories)

    def test_discovers_org_skills(self, repo_with_org_skills):
        result = discover_existing(repo_with_org_skills, org_name="myorg")
        assert result.has_existing
        # Should find org-knowledge SKILL.md and myrepo SKILL.md
        assert len(result.skills) >= 1
        org_skills = [s for s in result.skills if s.source == "org-skills"]
        assert len(org_skills) >= 1

    def test_discovers_engram_output(self, repo_with_engram_output):
        result = discover_existing(repo_with_engram_output)
        assert result.has_existing
        output_skills = [s for s in result.skills if s.source == "engram-output"]
        output_memories = [m for m in result.memories if m.source == "engram-output"]
        assert len(output_skills) >= 1
        assert len(output_memories) >= 1

    def test_empty_repo_no_existing(self, empty_repo):
        result = discover_existing(empty_repo)
        assert not result.has_existing
        assert result.total_items == 0

    def test_sources_tracked(self, repo_with_skills):
        result = discover_existing(repo_with_skills)
        assert len(result.sources_checked) >= 1
        assert any("repo:" in s for s in result.sources_checked)

    def test_content_read(self, repo_with_skills):
        result = discover_existing(repo_with_skills)
        arch_skills = result.skills_by_kind("architecture")
        assert len(arch_skills) == 1
        assert "FastAPI" in arch_skills[0].content

    def test_to_dict(self, repo_with_skills):
        result = discover_existing(repo_with_skills)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "skills" in d
        assert "memories" in d
        assert "sources_checked" in d
        assert "total_items" in d
        assert d["total_items"] == result.total_items


class TestExistingKnowledge:
    """Test ExistingKnowledge methods."""

    def test_summary_for_prompt(self, repo_with_skills):
        result = discover_existing(repo_with_skills)
        summary = result.summary_for_prompt()
        assert "EXISTING KNOWLEDGE" in summary
        assert "architecture" in summary.lower()

    def test_summary_empty(self):
        empty = ExistingKnowledge()
        assert empty.summary_for_prompt() == ""

    def test_skills_by_kind(self):
        existing = ExistingKnowledge(
            skills=[
                DiscoveredItem(path="architecture/SKILL.md", kind="skill", content="arch", source="repo"),
                DiscoveredItem(path="patterns/SKILL.md", kind="skill", content="patterns", source="repo"),
                DiscoveredItem(path="testing/SKILL.md", kind="skill", content="testing", source="repo"),
            ]
        )
        arch = existing.skills_by_kind("architecture")
        assert len(arch) == 1
        assert arch[0].path == "architecture/SKILL.md"

        test = existing.skills_by_kind("testing")
        assert len(test) == 1

    def test_has_existing_false(self):
        assert not ExistingKnowledge().has_existing

    def test_has_existing_true(self):
        e = ExistingKnowledge(skills=[
            DiscoveredItem(path="a.md", kind="skill", content="x", source="repo")
        ])
        assert e.has_existing


class TestDiscoveredItem:
    """Test DiscoveredItem dataclass."""

    def test_to_dict(self):
        item = DiscoveredItem(
            path="architecture/SKILL.md",
            kind="skill",
            content="# Architecture\nSome content here",
            source="repo",
            tier=2,
        )
        d = item.to_dict()
        assert d["path"] == "architecture/SKILL.md"
        assert d["kind"] == "skill"
        assert d["source"] == "repo"
        assert d["tier"] == 2
        assert d["content_length"] == len(item.content)
