# Engram CLI

AI-powered skill & memory generator for codebases. Fully local, no API keys needed.

## What it does

Point Engram at any codebase and it generates structured **skills** (architectural knowledge) and **memories** (exploration sessions) using a local AI model. Zero API cost, fully air-gapped.

```
$ engram analyze fastapi/fastapi

╭────────────────────────────────────────╮
│ Engram v2.0.0 - Local AI Code Analyzer │
╰────────────────────────────────────────╯

Phase 1: Heuristic Analysis
  Languages: Python (89%), Markdown (6%), Shell (3%)
  Frameworks: FastAPI, Starlette, Pydantic, Uvicorn, pytest
  Patterns: REST API, Middleware, Documentation site

Phase 2: Local Model Inference (qwen2.5-coder:7b)
  [1/5] Generating architecture skill...
  [2/5] Generating patterns skill...
  [3/5] Generating testing skill...
  [4/5] Generating project overview...
  [5/5] Generating activity analysis...

╭───────── Results for fastapi/fastapi ──────────╮
│ Generated 3 skills + 2 memories                │
│ Model: qwen2.5-coder:7b | Time: 42s | Cost: $0 │
╰────────────────────────────────────────────────╯
```

## Install

```bash
# 1. Install Ollama (one-time)
brew install ollama          # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh  # Linux

# 2. Install Engram CLI
pip install engram-cli
```

The first run will automatically download the Qwen2.5-Coder 7B model (~4.5GB, one-time).

## Usage

```bash
# Analyze current directory
engram analyze .

# Analyze a GitHub repo
engram analyze https://github.com/pallets/flask

# Shorthand
engram analyze pallets/flask

# Specify org name for output
engram analyze . --org mycompany/myrepo

# Use a larger model for better quality
engram analyze . --model qwen2.5-coder:14b

# Heuristic-only (no model, instant)
engram analyze . --skip-model

# JSON output for piping
engram analyze . --json-only | jq '.skills | length'

# List recommended models
engram models
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
        ├── 2026-02-13-myrepo-overview.md    # Project deep dive
        └── 2026-02-13-myrepo-activity.md    # Recent activity analysis
```

## How it works

### Layer 1: Heuristic Analysis (instant, no model)
- Walks the file tree, counts files/extensions
- Parses `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml` for dependencies
- Detects frameworks (React, FastAPI, Tokio, etc.) from dependency lists
- Identifies test infrastructure, CI/CD, Docker, K8s configs
- Extracts git metadata (commits, contributors, dates)
- Detects architectural patterns from directory structure

### Layer 2: Local Model Inference (~40s per repo)
- Feeds heuristic context into structured prompts
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
