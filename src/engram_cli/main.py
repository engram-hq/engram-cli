"""Engram CLI - AI-powered skill & memory generator for codebases.

Usage:
    engram analyze <repo-path-or-url> [options]
    engram analyze . --org mycompany
    engram analyze https://github.com/facebook/react
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.tree import Tree
from rich.markdown import Markdown

from . import __version__
from .analyzer import analyze_repo
from .model import OllamaClient, ModelError, DEFAULT_MODEL
from .generator import SkillMemoryGenerator

console = Console()


def _clone_repo(url: str, dest: Path) -> Path:
    """Clone a git repository to dest. Returns clone path."""
    # Parse GitHub URL to get org/repo
    import re
    match = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/\s#?]+)", url)
    if match:
        owner, repo = match.group(1), match.group(2).rstrip(".git")
        clone_dir = dest / repo
    else:
        clone_dir = dest / "repo"

    console.print(f"  Cloning {url}...", style="dim")
    result = subprocess.run(
        ["git", "clone", "--depth=50", "--single-branch", url, str(clone_dir)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise click.ClickException(f"Git clone failed: {result.stderr[:200]}")
    return clone_dir


def _resolve_repo_path(target: str) -> tuple[Path, str | None, bool]:
    """Resolve target to a local path. Returns (path, org_name, is_temp).

    Handles:
    - Local paths (., ./myrepo, /absolute/path)
    - GitHub URLs (https://github.com/owner/repo)
    - Shorthand (owner/repo)
    """
    # GitHub URL
    if "github.com/" in target or (
        "/" in target and not target.startswith("/") and not target.startswith(".")
        and not Path(target).exists()
    ):
        import re
        match = re.match(r"(?:https?://)?(?:github\.com/)?([^/]+)/([^/\s#?]+)", target)
        if match:
            owner, repo = match.group(1), match.group(2).rstrip(".git")
            url = f"https://github.com/{owner}/{repo}.git"
            tmpdir = Path(tempfile.mkdtemp(prefix="engram-"))
            clone_path = _clone_repo(url, tmpdir)
            return clone_path, f"{owner}/{repo}", True

    # Local path
    path = Path(target).resolve()
    if not path.is_dir():
        raise click.ClickException(f"Not a directory: {target}")
    return path, None, False


@click.group()
@click.version_option(version=__version__)
def cli():
    """Engram - AI-powered skill & memory generator for codebases.

    Analyze any repository to generate skills and memories using a local
    AI model. No API keys needed. Fully air-gapped.
    """
    pass


@cli.command()
@click.argument("target", default=".")
@click.option("--model", "-m", default=DEFAULT_MODEL, help="Ollama model name")
@click.option("--org", "-o", default=None, help="Organization name for output")
@click.option("--output", "-O", default=None, help="Output directory for generated files")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown", "both"]), default="both", help="Output format")
@click.option("--json-only", is_flag=True, help="Output raw JSON to stdout (for piping)")
@click.option("--skip-model", is_flag=True, help="Heuristic-only analysis, no model inference")
def analyze(target: str, model: str, org: str | None, output: str | None, fmt: str, json_only: bool, skip_model: bool):
    """Analyze a repository and generate skills + memories.

    TARGET can be a local path, GitHub URL, or owner/repo shorthand.

    Examples:

        engram analyze .

        engram analyze https://github.com/facebook/react

        engram analyze pallets/flask --org pallets

        engram analyze ./my-project --skip-model
    """
    is_temp = False
    try:
        # Resolve target
        if not json_only:
            console.print()
            console.print(Panel.fit(
                f"[bold cyan]Engram v{__version__}[/] - Local AI Code Analyzer",
                border_style="cyan",
            ))

        repo_path, detected_org, is_temp = _resolve_repo_path(target)
        org = org or detected_org or repo_path.name

        # Phase 1: Heuristic analysis
        if not json_only:
            console.print()
            console.print("[bold]Phase 1:[/] Heuristic Analysis", style="cyan")

        analysis = analyze_repo(repo_path)
        analysis.description = analysis.description or f"Repository: {org}"

        if not json_only:
            _print_analysis_summary(analysis)

        if skip_model:
            # Output heuristic-only results
            result_dict = {
                "analysis": analysis.to_dict(),
                "skills": [],
                "memories": [],
                "model_used": "none (heuristic only)",
            }
            if json_only:
                click.echo(json.dumps(result_dict, indent=2))
            else:
                console.print()
                console.print("[yellow]Skipped model inference (--skip-model)[/]")
                _print_heuristic_summary(analysis)
            return

        # Phase 2: Model inference
        if not json_only:
            console.print()
            console.print("[bold]Phase 2:[/] Local Model Inference", style="cyan")

        client = OllamaClient(model=model)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console if not json_only else Console(file=open(os.devnull, "w")),
        ) as progress:
            setup_task = progress.add_task("Setting up model...", total=None)

            def on_setup_progress(status, completed, total):
                progress.update(setup_task, description=status)

            try:
                client.ensure_ready(progress_callback=on_setup_progress)
            except ModelError as e:
                raise click.ClickException(str(e))

            progress.update(setup_task, description=f"Model ready: {model}", completed=True)

        # Generate skills and memories
        generator = SkillMemoryGenerator(client, org_name=org)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console if not json_only else Console(file=open(os.devnull, "w")),
        ) as progress:
            gen_task = progress.add_task("Generating...", total=5)

            def on_gen_progress(status, current, total):
                progress.update(gen_task, description=status, completed=current, total=total)

            result = generator.generate(analysis, progress_callback=on_gen_progress)
            progress.update(gen_task, description="Done!", completed=gen_task)

        # Output
        if json_only:
            click.echo(json.dumps(result.to_dict(), indent=2))
        else:
            _print_generation_result(result, org)
            if output or fmt in ("markdown", "both"):
                out_dir = Path(output) if output else Path(f"engram-output/{org}")
                _write_output(result, analysis, out_dir, fmt)
                console.print(f"\n[green]Output written to {out_dir}/[/]")

    finally:
        # Clean up temp clone
        if is_temp and repo_path:
            shutil.rmtree(repo_path.parent, ignore_errors=True)


@cli.command()
def models():
    """List available and recommended models."""
    console.print()
    console.print(Panel.fit("[bold cyan]Recommended Models[/]", border_style="cyan"))

    table = Table(show_header=True)
    table.add_column("Model", style="bold")
    table.add_column("Size", justify="right")
    table.add_column("RAM", justify="right")
    table.add_column("Quality", justify="center")
    table.add_column("Speed", justify="center")

    table.add_row("qwen2.5-coder:7b", "4.5GB", "8GB", "Good", "Fast", style="green")
    table.add_row("qwen2.5-coder:14b", "8.5GB", "16GB", "Very Good", "Medium")
    table.add_row("qwen2.5-coder:32b", "18GB", "24GB", "Excellent", "Slow")
    table.add_row("deepseek-coder-v2:16b", "9GB", "16GB", "Very Good", "Medium")
    table.add_row("codellama:13b", "7GB", "12GB", "Good", "Medium")

    console.print(table)
    console.print()
    console.print("Usage: [bold]engram analyze <repo> --model qwen2.5-coder:14b[/]")
    console.print()

    # Check Ollama status
    client = OllamaClient()
    if client.is_ollama_running():
        console.print("[green]Ollama is running[/]")
        try:
            import httpx
            resp = httpx.get(f"{client.base_url}/api/tags", timeout=5)
            models = resp.json().get("models", [])
            if models:
                console.print(f"Installed models: {', '.join(m['name'] for m in models)}")
            else:
                console.print("[yellow]No models installed. Run: ollama pull qwen2.5-coder:7b[/]")
        except Exception:
            pass
    else:
        console.print("[yellow]Ollama is not running. Start with: ollama serve[/]")


@cli.command()
def version():
    """Show version information."""
    console.print(f"engram-cli v{__version__}")
    console.print("Local AI-powered skill & memory generator")
    console.print("https://github.com/engram-hq/engram-cli")


def _print_analysis_summary(analysis) -> None:
    """Print a compact summary of the heuristic analysis."""
    table = Table(title="Repository Analysis", show_header=False, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Name", analysis.name)
    if analysis.description:
        table.add_row("Description", analysis.description[:80])
    table.add_row("Files / Dirs", f"{analysis.total_files:,} / {analysis.total_dirs:,}")

    if analysis.languages:
        langs = ", ".join(f"{k} ({v:.0f}%)" for k, v in sorted(analysis.languages.items(), key=lambda x: -x[1])[:5])
        table.add_row("Languages", langs)

    if analysis.frameworks:
        table.add_row("Frameworks", ", ".join(analysis.frameworks[:8]))

    if analysis.has_tests:
        table.add_row("Testing", f"{analysis.test_framework or 'detected'} ({analysis.test_file_count} files)")

    if analysis.has_ci:
        table.add_row("CI/CD", f"{analysis.ci_platform} ({len(analysis.ci_files)} workflows)")

    if analysis.has_docker:
        table.add_row("Docker", ", ".join(analysis.docker_files[:3]))

    if analysis.patterns:
        table.add_row("Patterns", ", ".join(analysis.patterns[:5]))

    if analysis.commit_count:
        table.add_row("Commits", f"{analysis.commit_count:,}")

    if analysis.contributors:
        table.add_row("Contributors", str(len(analysis.contributors)))

    if analysis.license_type:
        table.add_row("License", analysis.license_type)

    console.print(table)


def _print_heuristic_summary(analysis) -> None:
    """Print detailed heuristic analysis when --skip-model is used."""
    if analysis.top_dirs:
        tree = Tree("[bold]Directory Structure[/]")
        for d, count in sorted(analysis.top_dirs.items(), key=lambda x: -x[1])[:10]:
            tree.add(f"{d}/ ({count} files)")
        console.print(tree)

    if analysis.patterns:
        console.print()
        console.print("[bold]Detected Patterns:[/]")
        for p in analysis.patterns:
            console.print(f"  - {p}")


def _print_generation_result(result, org: str) -> None:
    """Print generation results."""
    console.print()
    console.print(Panel.fit(
        f"[bold green]Generated {len(result.skills)} skills + {len(result.memories)} memories[/]\n"
        f"Model: {result.model_used} | Time: {result.generation_time_seconds:.1f}s | Cost: $0.00",
        border_style="green",
        title=f"Results for {org}",
    ))

    if result.skills:
        console.print()
        console.print("[bold]Skills:[/]")
        for s in result.skills:
            words = len(s.content.split())
            console.print(f"  [cyan]{s.path}[/] ({words} words)")

    if result.memories:
        console.print()
        console.print("[bold]Memories:[/]")
        for m in result.memories:
            words = len(m.content.split())
            console.print(f"  [magenta]{m.path}[/] ({words} words)")

    if result.errors:
        console.print()
        console.print("[bold red]Errors:[/]")
        for e in result.errors:
            console.print(f"  [red]{e}[/]")


def _write_output(result, analysis, out_dir: Path, fmt: str) -> None:
    """Write output files."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt in ("json", "both"):
        # Write combined JSON
        combined = {
            "analysis": analysis.to_dict(),
            **result.to_dict(),
        }
        (out_dir / "engram-analysis.json").write_text(json.dumps(combined, indent=2))

    if fmt in ("markdown", "both"):
        # Write individual skill files
        skills_dir = out_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for s in result.skills:
            skill_path = skills_dir / s.path
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(s.content)

        # Write individual memory files
        memories_dir = out_dir / "memories"
        memories_dir.mkdir(exist_ok=True)
        for m in result.memories:
            mem_path = memories_dir / m.path
            mem_path.parent.mkdir(parents=True, exist_ok=True)
            mem_path.write_text(m.content)


if __name__ == "__main__":
    cli()
