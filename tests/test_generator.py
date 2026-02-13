"""Tests for the skill/memory generator."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from engram_cli.analyzer import analyze_repo, RepoAnalysis
from engram_cli.generator import (
    SkillMemoryGenerator,
    GeneratedSkill,
    GeneratedMemory,
    GenerationResult,
    _ensure_frontmatter,
)
from engram_cli.model import OllamaClient


@pytest.fixture
def mock_client():
    """Create a mock OllamaClient that returns structured responses."""
    client = MagicMock(spec=OllamaClient)
    client.model = "qwen2.5-coder:7b"

    def side_effect(prompt, system="", temperature=0.3, max_tokens=4096):
        if "architecture" in prompt.lower():
            return """---
name: test-architecture
description: Test architecture
last_updated: 2026-02-13
---

# Architecture

## Overview
This is a test application built with Python and FastAPI.

## Key Design Decisions
- FastAPI for async performance
- SQLAlchemy for ORM
- Clean architecture with service layer

## Module Structure
- src/: Application source code
- tests/: Test suite
- docs/: Documentation"""

        elif "pattern" in prompt.lower():
            return """---
name: test-patterns
description: Code patterns
last_updated: 2026-02-13
---

# Patterns & Conventions

## Code Organization
Standard Python package layout with src/ directory.

## Error Handling
Exception-based with custom error types.

## Testing Patterns
Pytest with fixtures and conftest."""

        elif "testing" in prompt.lower() or "test" in prompt.lower():
            return """---
name: test-testing
description: Testing strategy
last_updated: 2026-02-13
---

# Testing Strategy

## Framework & Tools
pytest with fixtures

## Test Organization
tests/ directory with conftest.py"""

        elif "overview" in prompt.lower() or "explored" in prompt.lower():
            return """---
date: 2026-02-13
type: exploration
model: engram-local
cost_usd: 0
---

# Session: Test Deep Dive

## Summary
Explored test repository. Found Python FastAPI application.

## Key Takeaways
- Well-structured codebase
- Good test coverage"""

        elif "activity" in prompt.lower() or "commit" in prompt.lower():
            return """---
date: 2026-02-13
type: activity-analysis
model: engram-local
cost_usd: 0
---

# Session: Test Activity Analysis

## Summary
Active development with regular commits.

## Active Development Areas
- API endpoints
- Test coverage"""

        return "Generated content"

    client.generate.side_effect = side_effect
    return client


@pytest.fixture
def sample_repo(tmp_path):
    """Create a sample repo for testing."""
    (tmp_path / "README.md").write_text("# Test Project\nA test project\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndescription = "Test"\n'
        'dependencies = ["fastapi", "pytest"]\n'
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("from fastapi import FastAPI\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text("import pytest\n")
    (tests / "test_main.py").write_text("def test_it(): pass\n")
    return tmp_path


class TestSkillMemoryGenerator:
    """Test the generator with mocked model."""

    def test_generate_produces_skills_and_memories(self, mock_client, sample_repo):
        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(mock_client, org_name="test-org")
        result = generator.generate(analysis)

        assert isinstance(result, GenerationResult)
        assert len(result.skills) >= 2  # architecture + patterns
        assert len(result.memories) >= 1  # overview
        assert result.model_used == "qwen2.5-coder:7b"
        assert result.generation_time_seconds >= 0

    def test_skill_structure(self, mock_client, sample_repo):
        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(mock_client, org_name="test-org")
        result = generator.generate(analysis)

        arch_skill = next(s for s in result.skills if "architecture" in s.path)
        assert arch_skill.org == "test-org"
        assert arch_skill.tier == 2
        assert arch_skill.content.startswith("---")
        assert "Architecture" in arch_skill.content

    def test_memory_structure(self, mock_client, sample_repo):
        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(mock_client, org_name="test-org")
        result = generator.generate(analysis)

        overview = next(m for m in result.memories if "overview" in m.path)
        assert overview.org == "test-org"
        assert overview.repo == ".memory"
        assert overview.content.startswith("---")

    def test_testing_skill_generated_when_tests_exist(self, mock_client, sample_repo):
        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(mock_client, org_name="test-org")
        result = generator.generate(analysis)

        testing_skills = [s for s in result.skills if "testing" in s.path]
        assert len(testing_skills) == 1

    def test_to_dict(self, mock_client, sample_repo):
        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(mock_client, org_name="test-org")
        result = generator.generate(analysis)

        d = result.to_dict()
        assert isinstance(d, dict)
        assert "skills" in d
        assert "memories" in d
        assert "model_used" in d
        assert all(isinstance(s, dict) for s in d["skills"])

    def test_progress_callback(self, mock_client, sample_repo):
        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(mock_client, org_name="test-org")
        progress_calls = []

        def callback(msg, current, total):
            progress_calls.append((msg, current, total))

        result = generator.generate(analysis, progress_callback=callback)
        assert len(progress_calls) >= 3  # at least arch + patterns + overview

    def test_error_handling(self, sample_repo):
        client = MagicMock(spec=OllamaClient)
        client.model = "test-model"
        client.generate.side_effect = Exception("Model crashed")

        analysis = analyze_repo(sample_repo)
        generator = SkillMemoryGenerator(client, org_name="test-org")
        result = generator.generate(analysis)

        assert len(result.errors) > 0
        assert "Model crashed" in result.errors[0]


class TestEnsureFrontmatter:
    """Test frontmatter helper."""

    def test_adds_frontmatter_when_missing(self):
        content = "# Title\n\nSome content"
        result = _ensure_frontmatter(content, {"name": "test", "date": "2026-01-01"})
        assert result.startswith("---\n")
        assert "name: test" in result
        assert "# Title" in result

    def test_preserves_existing_frontmatter(self):
        content = "---\nname: existing\n---\n# Title"
        result = _ensure_frontmatter(content, {"name": "new"})
        assert "name: existing" in result
        assert "name: new" not in result

    def test_handles_empty_content(self):
        result = _ensure_frontmatter("", {"name": "test"})
        assert result.startswith("---\n")
        assert "name: test" in result
