# Engram CLI

AI-powered skill & memory generator for codebases. Fully local, no API keys needed.

## What it does

Point Engram at any codebase and it generates structured **skills** (architectural knowledge) and **memories** (exploration sessions) using a local AI model. Zero API cost, fully air-gapped.

**New in v3.0:** Engram now performs **additive analysis** — it discovers existing skills and memories in your repo and builds upon them, instead of generating from scratch every time.

```
$ engram analyze .

╭───────────────────────────────────────╮
│ Engram v3.0.0 - Local AI Code Analyzer │
╰───────────────────────────────────────╯

Phase 1: Heuristic Analysis
  Languages: Python (89%), Markdown (6%), Shell (3%)
  Frameworks: FastAPI, Starlette, Pydantic, Uvicorn, pytest
  Patterns: REST API, Middleware, Documentation site

Discovery: Scanning for existing knowledge...
  Found 4 existing skills and 6 existing memories - will use additive mode

Phase 2: Local Model Inference (Additive mode)
  [1/5] Generating architecture skill...
  [2/5] Generating patterns skill...
  [3/5] Generating testing skill...
  [4/5] Generating project overview...
  [5/5] Generating activity analysis...

╭───────── Results for myproject ──────────╮
│ Generated 3 skills + 2 memories (ADDITIVE) │
│ Model: qwen2.5-coder:7b | Time: 42s | Cost: $0 │
╰─────────────────────────────────────────╯
```

## Install

```bash
# 1. Install Ollama (one-time)
brew install ollama          # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh  # Linux

# 2. Install Engram CLI
brew install pipx && pipx install engram-cli   # macOS (recommended)
# or: pip install engram-cli                   # Linux / virtualenv
```

The first run will automatically download the Qwen2.5-Coder 7B model (~4.5GB, one-time).

## Usage

```bash
# Analyze current directory (auto-discovers existing skills/memories)
engram analyze .

# Analyze a GitHub repo
engram analyze https://github.com/pallets/flask

# Shorthand
engram analyze pallets/flask

# Specify org name for output
engram analyze . --org mycompany/myrepo

# Force fresh analysis (ignore existing skills/memories)
engram analyze . --fresh

# Use a larger model for better quality
engram analyze . --model qwen2.5-coder:14b

# Heuristic-only (no model, instant)
engram analyze . --skip-model

# JSON output for piping
engram analyze . --json-only | jq '.skills | length'

# List recommended models
engram models

# Browse analysis results in a local web viewer
engram browse

# Start the viewer server without opening browser
engram serve

# Check version
engram version
```

## Additive Analysis

By default, Engram scans your repo for existing skills and memories before generating new ones. It searches:

1. **Repo-level directories** — `.skills/`, `.memory/`, `skills/`, `memories/`
2. **Org-level skills repos** — sibling `{org}-skills/` directories
3. **Previous Engram output** — `engram-output/` from prior runs
4. **Claude Code auto-memory** — `~/.claude/projects/*/memory/`

When existing knowledge is found, Engram switches to **additive mode**:

- Existing content is fed into the model prompts as context
- The model is instructed to **update** stale information, **add** missing insights, and **preserve** what's still accurate
- The result builds on your accumulated knowledge instead of replacing it

Use `--fresh` to skip discovery and generate from scratch:

```bash
engram analyze . --fresh
```

## Output

By default, outputs both JSON and Markdown:

```
engram-output/myrepo/
├── engram-analysis.json          # Combined analysis + generated content
├── skills/
│   ├── architecture/SKILL.md     # Architecture overview
│   ├── patterns/SKILL.md         # Code patterns & conventions
│   └── testing/SKILL.md          # Testing strategy (if tests detected)
└── memories/
    └── sessions/
        ├── 2026-03-16-myrepo-overview.md    # Project deep dive
        └── 2026-03-16-myrepo-activity.md    # Recent activity analysis
```

## Visual Browser

After analyzing repos, browse results in a local web UI with 5 tabs: Skills, Timeline (3D graph), Search, Analytics, and Sync.

```bash
# Analyze a few repos first
engram analyze .
engram analyze https://github.com/fastapi/fastapi

# Open the visual browser (auto-opens in your default browser)
engram browse

# Or start the server without opening browser
engram serve
# Then open http://localhost:8420
```

The viewer aggregates all repos in `engram-output/` into a single dashboard. Fully air-gapped - no network requests except for loading the 3D graph library.

## How it works

### Layer 0: Discovery (instant, no model)
- Scans repo, sibling org-skills repos, previous output, and Claude memory
- Loads existing skill/memory content for additive context
- Determines whether to use additive or fresh mode

### Layer 1: Heuristic Analysis (instant, no model)
- Walks the file tree, counts files/extensions
- Parses `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml` for dependencies
- Detects frameworks (React, FastAPI, Tokio, etc.) from dependency lists
- Identifies test infrastructure, CI/CD, Docker, K8s configs
- Extracts git metadata (commits, contributors, dates)
- Detects architectural patterns from directory structure

### Layer 2: Local Model Inference (~40s per repo)
- Feeds heuristic context + existing knowledge into structured prompts
- In additive mode, prompts instruct the model to merge with existing content
- Qwen2.5-Coder 7B generates natural language skills and memories
- Produces architecture overviews, pattern analysis, testing guides
- Session memories document the exploration findings

## Models

| Model | Size | RAM | Quality | Speed |
|-------|------|-----|---------|-------|
| `qwen2.5-coder:7b` (default) | 4.5GB | 8GB | Good | ~30 tok/s |
| `qwen2.5-coder:14b` | 8.5GB | 16GB | Very Good | ~18 tok/s |
| `qwen2.5-coder:32b` | 18GB | 24GB | Excellent | ~10 tok/s |
| `deepseek-coder-v2:16b` | 9GB | 16GB | Very Good | ~18 tok/s |

## Development

```bash
git clone https://github.com/engram-hq/engram-cli
cd engram-cli
python -m venv .venv && source .venv/bin/activate
pip install ".[dev]"
pytest tests/ -v
```

## License

MIT
