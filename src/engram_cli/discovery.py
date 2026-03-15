"""Discover existing skills and memories in a repository.

Scans known locations for pre-existing skill and memory files
so the generator can produce additive (not from-scratch) output.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DiscoveredItem:
    """A single discovered skill or memory file."""

    path: str  # relative path from discovery root
    kind: str  # "skill" or "memory"
    content: str  # full file content (truncated for prompt injection)
    source: str  # where it was found: "repo", "org-skills", "engram-output", "claude-memory"
    tier: int = 0  # skill tier (1=user, 2=org, 3=repo)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "source": self.source,
            "tier": self.tier,
            "content_length": len(self.content),
        }


@dataclass
class ExistingKnowledge:
    """All discovered existing skills and memories for a repo."""

    skills: list[DiscoveredItem] = field(default_factory=list)
    memories: list[DiscoveredItem] = field(default_factory=list)
    sources_checked: list[str] = field(default_factory=list)

    @property
    def has_existing(self) -> bool:
        return bool(self.skills or self.memories)

    @property
    def total_items(self) -> int:
        return len(self.skills) + len(self.memories)

    def skills_by_kind(self, name_pattern: str) -> list[DiscoveredItem]:
        """Filter skills matching a name pattern (e.g., 'architecture', 'pattern')."""
        return [
            s for s in self.skills if name_pattern.lower() in s.path.lower()
        ]

    def summary_for_prompt(self, max_chars: int = 6000) -> str:
        """Generate a concise summary of existing knowledge for LLM context."""
        if not self.has_existing:
            return ""

        lines = []
        lines.append(f"EXISTING KNOWLEDGE ({len(self.skills)} skills, {len(self.memories)} memories):")
        lines.append("")

        # Skills
        char_budget = max_chars
        for item in self.skills:
            header = f"--- Existing Skill: {item.path} (tier {item.tier}, source: {item.source}) ---"
            # Truncate content to fit budget
            available = max(200, char_budget // max(1, len(self.skills) + len(self.memories)))
            content = item.content[:available]
            block = f"{header}\n{content}\n"
            lines.append(block)
            char_budget -= len(block)
            if char_budget <= 0:
                break

        # Memories
        for item in self.memories:
            header = f"--- Existing Memory: {item.path} (source: {item.source}) ---"
            available = max(200, char_budget // max(1, len(self.memories)))
            content = item.content[:available]
            block = f"{header}\n{content}\n"
            lines.append(block)
            char_budget -= len(block)
            if char_budget <= 0:
                break

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": [s.to_dict() for s in self.skills],
            "memories": [m.to_dict() for m in self.memories],
            "sources_checked": self.sources_checked,
            "total_items": self.total_items,
        }


# Directories within a repo that may contain skills
SKILL_DIRS = [".skills", "skills", ".engram/skills"]

# Directories within a repo that may contain memories
MEMORY_DIRS = [".memory", "memories", ".engram/memories"]

# Max file size to read (skip huge files)
MAX_FILE_SIZE = 50_000

# Skill/memory file extensions
CONTENT_EXTENSIONS = {".md", ".yaml", ".yml"}


def discover_existing(
    repo_path: Path,
    org_name: str | None = None,
) -> ExistingKnowledge:
    """Discover existing skills and memories for a repository.

    Searches these locations in order:
    1. Skill/memory dirs inside the repo itself
    2. Sibling '{org}-skills' directory (org-level skills repo)
    3. Previous engram-output for this repo
    4. Claude auto-memory for this project
    """
    result = ExistingKnowledge()
    repo_path = Path(repo_path).resolve()
    repo_name = repo_path.name

    # 1. Inside the repo
    _scan_repo_dirs(repo_path, result)

    # 2. Sibling org-skills repo
    _scan_org_skills(repo_path, org_name, repo_name, result)

    # 3. Previous engram-output
    _scan_engram_output(repo_path, org_name, repo_name, result)

    # 4. Claude auto-memory
    _scan_claude_memory(repo_path, result)

    return result


def _scan_repo_dirs(repo_path: Path, result: ExistingKnowledge) -> None:
    """Scan skill/memory directories inside the repo."""
    source = "repo"
    result.sources_checked.append(f"repo:{repo_path}")

    for skill_dir in SKILL_DIRS:
        dirpath = repo_path / skill_dir
        if dirpath.is_dir():
            _collect_files(dirpath, "skill", source, result, base_path=repo_path)

    for mem_dir in MEMORY_DIRS:
        dirpath = repo_path / mem_dir
        if dirpath.is_dir():
            _collect_files(dirpath, "memory", source, result, base_path=repo_path)


def _scan_org_skills(
    repo_path: Path,
    org_name: str | None,
    repo_name: str,
    result: ExistingKnowledge,
) -> None:
    """Scan sibling org-skills directory."""
    parent = repo_path.parent

    # Try patterns: {org}-skills, {org}_skills
    candidates = []
    if org_name:
        # Handle "owner/repo" format
        org_base = org_name.split("/")[0] if "/" in org_name else org_name
        candidates.append(parent / f"{org_base}-skills")
        candidates.append(parent / f"{org_base}_skills")

    # Also try generic patterns
    for entry in parent.iterdir():
        if entry.is_dir() and entry.name.endswith("-skills") and entry not in candidates:
            candidates.append(entry)

    for skills_dir in candidates:
        if not skills_dir.is_dir():
            continue
        result.sources_checked.append(f"org-skills:{skills_dir}")

        # Look for repo-specific skills within the org skills repo
        # Common structures: {repo}/, org-knowledge/, repo-knowledge/
        for subdir in [repo_name, "org-knowledge", "repo-knowledge"]:
            sub = skills_dir / subdir
            if sub.is_dir():
                _collect_files(sub, "skill", "org-skills", result, base_path=skills_dir, tier=2)

        # Also scan root-level skill files
        _collect_files(skills_dir, "skill", "org-skills", result, base_path=skills_dir, tier=2, recurse=False)


def _scan_engram_output(
    repo_path: Path,
    org_name: str | None,
    repo_name: str,
    result: ExistingKnowledge,
) -> None:
    """Scan previous engram-output directories."""
    # Check engram-output in current dir, repo parent, and repo itself
    candidates = [
        repo_path / "engram-output",
        repo_path.parent / "engram-output",
    ]

    for output_dir in candidates:
        if not output_dir.is_dir():
            continue

        # Try org-specific subdirs
        search_dirs = [output_dir / repo_name]
        if org_name:
            search_dirs.insert(0, output_dir / org_name)

        for search in search_dirs:
            if not search.is_dir():
                continue
            result.sources_checked.append(f"engram-output:{search}")

            skills_dir = search / "skills"
            if skills_dir.is_dir():
                _collect_files(skills_dir, "skill", "engram-output", result, base_path=search)

            memories_dir = search / "memories"
            if memories_dir.is_dir():
                _collect_files(memories_dir, "memory", "engram-output", result, base_path=search)


def _scan_claude_memory(repo_path: Path, result: ExistingKnowledge) -> None:
    """Scan Claude Code auto-memory for this project."""
    home = Path.home()
    claude_projects = home / ".claude" / "projects"
    if not claude_projects.is_dir():
        return

    # Claude stores memories under a path-hash like:
    # ~/.claude/projects/-Users-foo-src-myrepo/memory/
    # Convert repo_path to the Claude key format
    repo_key = str(repo_path).replace("/", "-")
    if repo_key.startswith("-"):
        pass  # expected

    for project_dir in claude_projects.iterdir():
        if not project_dir.is_dir():
            continue
        # Check if this project dir matches our repo path
        if project_dir.name != repo_key:
            continue

        memory_dir = project_dir / "memory"
        if memory_dir.is_dir():
            result.sources_checked.append(f"claude-memory:{memory_dir}")
            _collect_files(memory_dir, "memory", "claude-memory", result, base_path=memory_dir)


def _collect_files(
    dirpath: Path,
    kind: str,
    source: str,
    result: ExistingKnowledge,
    base_path: Path,
    tier: int = 0,
    recurse: bool = True,
) -> None:
    """Collect skill or memory files from a directory."""
    if not dirpath.is_dir():
        return

    walker = os.walk(dirpath) if recurse else [(str(dirpath), [], os.listdir(dirpath))]

    for root, dirs, files in walker:
        # Skip hidden dirs and common noise
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", ".git"}]

        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in CONTENT_EXTENSIONS:
                continue

            fpath = Path(root) / fname
            if not fpath.is_file():
                continue

            # Skip files that are too large
            try:
                size = fpath.stat().st_size
                if size > MAX_FILE_SIZE or size == 0:
                    continue
            except OSError:
                continue

            try:
                content = fpath.read_text(errors="replace")
            except Exception:
                continue

            rel_path = str(fpath.relative_to(base_path))

            # Infer tier from path if not set
            item_tier = tier
            if item_tier == 0:
                item_tier = _infer_tier(rel_path, source)

            item = DiscoveredItem(
                path=rel_path,
                kind=kind,
                content=content,
                source=source,
                tier=item_tier,
            )

            if kind == "skill":
                result.skills.append(item)
            else:
                result.memories.append(item)


def _infer_tier(path: str, source: str) -> int:
    """Infer skill tier from path and source."""
    lower = path.lower()
    if source == "claude-memory":
        return 1  # user-level
    if source == "org-skills":
        if "org-knowledge" in lower:
            return 2  # org-level
        return 2
    if "tier-1" in lower or "user" in lower:
        return 1
    if "tier-2" in lower or "org" in lower:
        return 2
    if "tier-3" in lower or "repo" in lower:
        return 3
    return 2  # default to org tier
