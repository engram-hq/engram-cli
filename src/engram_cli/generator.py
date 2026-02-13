"""Skill and memory generator - combines Layer 1 + Layer 2.

Takes heuristic analysis, feeds into prompt templates,
calls local model, returns structured skill/memory objects.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from .analyzer import RepoAnalysis
from .model import OllamaClient
from .prompts import (
    SYSTEM_PROMPT,
    activity_memory_prompt,
    architecture_skill_prompt,
    overview_memory_prompt,
    patterns_skill_prompt,
    testing_skill_prompt,
)


@dataclass
class GeneratedSkill:
    """A generated skill document."""

    org: str
    repo: str
    tier: int
    path: str
    name: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "org": self.org,
            "repo": self.repo,
            "tier": self.tier,
            "path": self.path,
            "name": self.name,
            "content": self.content,
        }


@dataclass
class GeneratedMemory:
    """A generated memory document."""

    org: str
    repo: str
    path: str
    name: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "org": self.org,
            "repo": self.repo,
            "path": self.path,
            "name": self.name,
            "content": self.content,
        }


@dataclass
class GenerationResult:
    """Complete generation output."""

    skills: list[GeneratedSkill] = field(default_factory=list)
    memories: list[GeneratedMemory] = field(default_factory=list)
    model_used: str = ""
    generation_time_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": [s.to_dict() for s in self.skills],
            "memories": [m.to_dict() for m in self.memories],
            "model_used": self.model_used,
            "generation_time_seconds": round(self.generation_time_seconds, 1),
            "errors": self.errors,
        }


class SkillMemoryGenerator:
    """Generates skills and memories from repository analysis."""

    def __init__(self, client: OllamaClient, org_name: str | None = None):
        self.client = client
        self.org_name = org_name

    def generate(
        self,
        analysis: RepoAnalysis,
        progress_callback=None,
    ) -> GenerationResult:
        """Generate all skills and memories for a repo analysis."""
        import time

        start = time.time()

        result = GenerationResult(model_used=self.client.model)
        org = self.org_name or analysis.name
        repo = analysis.name
        today = datetime.date.today().isoformat()
        context = analysis.summary_for_prompt()

        steps = self._plan_steps(analysis)
        total = len(steps)

        for i, (step_name, step_func) in enumerate(steps):
            if progress_callback:
                progress_callback(f"Generating {step_name}...", i + 1, total)
            try:
                item = step_func(analysis, context, org, repo, today)
                if isinstance(item, GeneratedSkill):
                    result.skills.append(item)
                elif isinstance(item, GeneratedMemory):
                    result.memories.append(item)
            except Exception as e:
                result.errors.append(f"{step_name}: {str(e)}")

        result.generation_time_seconds = time.time() - start
        return result

    def _plan_steps(self, analysis: RepoAnalysis) -> list[tuple[str, Any]]:
        """Determine which skills/memories to generate based on analysis."""
        steps = []

        # Always generate architecture and overview
        steps.append(("architecture skill", self._gen_architecture))
        steps.append(("patterns skill", self._gen_patterns))

        # Conditional skills
        if analysis.has_tests:
            steps.append(("testing skill", self._gen_testing))

        # Always generate overview memory
        steps.append(("project overview", self._gen_overview_memory))

        # Activity memory if we have commits
        if analysis.recent_commits:
            steps.append(("activity analysis", self._gen_activity_memory))

        return steps

    def _gen_architecture(
        self,
        analysis: RepoAnalysis,
        context: str,
        org: str,
        repo: str,
        today: str,
    ) -> GeneratedSkill:
        prompt = architecture_skill_prompt(context, analysis.readme_excerpt)
        content = self.client.generate(prompt, system=SYSTEM_PROMPT)
        content = _ensure_frontmatter(
            content,
            {
                "name": f"{repo}-architecture",
                "description": f"Architecture overview for {repo}",
                "last_updated": today,
            },
        )
        return GeneratedSkill(
            org=org,
            repo=repo,
            tier=2,
            path="architecture/SKILL.md",
            name="architecture.md",
            content=content,
        )

    def _gen_patterns(
        self,
        analysis: RepoAnalysis,
        context: str,
        org: str,
        repo: str,
        today: str,
    ) -> GeneratedSkill:
        key_files = "\n".join(
            f"--- {name} ---\n{content[:1000]}"
            for name, content in list(analysis.key_file_contents.items())[:3]
        )
        prompt = patterns_skill_prompt(context, key_files)
        content = self.client.generate(prompt, system=SYSTEM_PROMPT)
        content = _ensure_frontmatter(
            content,
            {
                "name": f"{repo}-patterns",
                "description": f"Code patterns and conventions for {repo}",
                "last_updated": today,
            },
        )
        return GeneratedSkill(
            org=org,
            repo=repo,
            tier=2,
            path="patterns/SKILL.md",
            name="patterns.md",
            content=content,
        )

    def _gen_testing(
        self,
        analysis: RepoAnalysis,
        context: str,
        org: str,
        repo: str,
        today: str,
    ) -> GeneratedSkill:
        prompt = testing_skill_prompt(context)
        content = self.client.generate(prompt, system=SYSTEM_PROMPT)
        content = _ensure_frontmatter(
            content,
            {
                "name": f"{repo}-testing",
                "description": f"Testing strategy for {repo}",
                "last_updated": today,
            },
        )
        return GeneratedSkill(
            org=org,
            repo=repo,
            tier=2,
            path="testing/SKILL.md",
            name="testing.md",
            content=content,
        )

    def _gen_overview_memory(
        self,
        analysis: RepoAnalysis,
        context: str,
        org: str,
        repo: str,
        today: str,
    ) -> GeneratedMemory:
        prompt = overview_memory_prompt(context, analysis.readme_excerpt)
        content = self.client.generate(prompt, system=SYSTEM_PROMPT)
        content = _ensure_frontmatter(
            content,
            {
                "date": today,
                "type": "exploration",
                "model": f"engram-local ({self.client.model})",
                "cost_usd": "0",
            },
        )
        fname = f"{today}-{repo}-overview.md"
        return GeneratedMemory(
            org=org,
            repo=".memory",
            path=f"sessions/{fname}",
            name=fname,
            content=content,
        )

    def _gen_activity_memory(
        self,
        analysis: RepoAnalysis,
        context: str,
        org: str,
        repo: str,
        today: str,
    ) -> GeneratedMemory:
        commits_text = "\n".join(
            f"- {c['date']} {c['author']}: {c['message']}"
            for c in analysis.recent_commits[:20]
        )
        prompt = activity_memory_prompt(context, commits_text)
        content = self.client.generate(prompt, system=SYSTEM_PROMPT)
        content = _ensure_frontmatter(
            content,
            {
                "date": today,
                "type": "activity-analysis",
                "model": f"engram-local ({self.client.model})",
                "cost_usd": "0",
            },
        )
        fname = f"{today}-{repo}-activity.md"
        return GeneratedMemory(
            org=org,
            repo=".memory",
            path=f"sessions/{fname}",
            name=fname,
            content=content,
        )


def _ensure_frontmatter(content: str, defaults: dict[str, str]) -> str:
    """Ensure content has valid YAML frontmatter."""
    content = content.strip()

    # If model already produced frontmatter, return as-is
    if content.startswith("---"):
        return content

    # Prepend default frontmatter
    fm_lines = ["---"]
    for k, v in defaults.items():
        fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    fm_lines.append("")

    return "\n".join(fm_lines) + content
