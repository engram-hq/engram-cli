"""Prompt templates for skill and memory generation.

Each template takes heuristic analysis context and generates
a focused, structured prompt for the local model.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are an expert software architect analyzing codebases.
Generate precise, actionable technical documentation in markdown format.
Focus on architectural insights, not obvious facts.
Be specific about patterns, trade-offs, and design decisions.
Use concrete details from the provided analysis data.
Write in a professional technical style, not promotional."""


def architecture_skill_prompt(context: str, readme_excerpt: str = "") -> str:
    """Generate prompt for architecture skill."""
    return f"""Analyze this repository and write a concise architecture skill document.

REPOSITORY ANALYSIS:
{context}

{f"README EXCERPT:{chr(10)}{readme_excerpt[:1500]}" if readme_excerpt else ""}

Write a skill document with this EXACT structure (include the YAML frontmatter):

---
name: <repo-name>-architecture
description: <one-line description>
last_updated: <today's date>
---

# Architecture

## Overview
<2-3 sentences: what this project does and its core architectural approach>

## Key Design Decisions
<3-5 bullet points about WHY the architecture was chosen, trade-offs made>

## Module Structure
<describe the main modules/packages and their responsibilities>

## Data Flow
<how data flows through the system, key abstractions>

## Dependencies & Integration Points
<critical external dependencies and how they're used>

Keep it under 600 words. Focus on insights an engineer needs to understand the codebase quickly."""


def patterns_skill_prompt(context: str, key_files_summary: str = "") -> str:
    """Generate prompt for patterns/conventions skill."""
    return f"""Analyze this repository's patterns and conventions.

REPOSITORY ANALYSIS:
{context}

{f"KEY FILES:{chr(10)}{key_files_summary[:2000]}" if key_files_summary else ""}

Write a skill document with this EXACT structure:

---
name: <repo-name>-patterns
description: Code patterns and conventions
last_updated: <today's date>
---

# Patterns & Conventions

## Code Organization
<how code is structured: naming, file layout, module boundaries>

## Error Handling
<error handling approach: Result types, exceptions, error boundaries>

## Testing Patterns
<test organization, fixtures, mocking strategy>

## Configuration
<how config is managed: env vars, config files, feature flags>

## Common Patterns
<3-5 recurring patterns in the codebase with brief examples>

Keep it under 500 words. Be specific to THIS project, not generic advice."""


def testing_skill_prompt(context: str) -> str:
    """Generate prompt for testing skill."""
    return f"""Analyze the testing infrastructure of this repository.

REPOSITORY ANALYSIS:
{context}

Write a skill document with this EXACT structure:

---
name: <repo-name>-testing
description: Test infrastructure and strategy
last_updated: <today's date>
---

# Testing Strategy

## Framework & Tools
<test framework, assertion libraries, mocking tools>

## Test Organization
<where tests live, naming conventions, test categories>

## Running Tests
<commands to run tests: unit, integration, e2e>

## Coverage & CI
<how coverage is tracked, CI integration>

## Key Testing Patterns
<fixture patterns, factory functions, test helpers>

Keep it under 400 words."""


def overview_memory_prompt(context: str, readme_excerpt: str = "") -> str:
    """Generate prompt for project overview memory (session-style)."""
    return f"""You explored this repository. Write a session memory documenting your findings.

REPOSITORY ANALYSIS:
{context}

{f"README:{chr(10)}{readme_excerpt[:1500]}" if readme_excerpt else ""}

Write a session memory with this EXACT structure:

---
date: <today's date>
type: exploration
model: engram-local
cost_usd: 0
input_tokens: 0
output_tokens: 0
---

# Session: <repo-name> Deep Dive

## Summary
<2-3 sentences: what was explored, key findings>

## Architecture Insights
<3-5 key architectural observations with specifics>

## Notable Patterns
<interesting patterns discovered, with reasoning about WHY they were chosen>

## Strengths
<2-3 technical strengths of the project>

## Areas to Watch
<2-3 areas of complexity or potential technical debt>

## Key Takeaways
<3-5 bullet points an engineer should remember>

Keep it under 500 words. Write as if documenting a real exploration session."""


def activity_memory_prompt(context: str, commits_text: str) -> str:
    """Generate prompt for recent activity memory."""
    return f"""Analyze the recent commit activity for this repository.

REPOSITORY ANALYSIS:
{context}

RECENT COMMITS:
{commits_text[:3000]}

Write a session memory with this EXACT structure:

---
date: <today's date>
type: activity-analysis
model: engram-local
cost_usd: 0
---

# Session: <repo-name> Activity Analysis

## Summary
<2-3 sentences: development velocity, focus areas>

## Active Development Areas
<which parts of the codebase are being actively changed, with specific examples>

## Patterns in Commits
<commit message style, PR patterns, release cadence>

## Key Contributors
<who is most active and in what areas>

Keep it under 400 words."""
