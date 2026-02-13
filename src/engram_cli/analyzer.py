"""Heuristic code analyzer - Layer 1. No model needed.

Parses repo structure, detects languages/frameworks/patterns,
reads manifests, identifies tests/CI/Docker, extracts code metrics.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RepoAnalysis:
    """Complete heuristic analysis of a repository."""

    path: str
    name: str
    description: str = ""

    # Structure
    total_files: int = 0
    total_dirs: int = 0
    top_dirs: dict[str, int] = field(default_factory=dict)
    file_extensions: dict[str, int] = field(default_factory=dict)

    # Languages & frameworks
    languages: dict[str, float] = field(default_factory=dict)  # lang -> percentage
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)

    # Dependencies
    dependencies: dict[str, list[str]] = field(default_factory=dict)  # category -> list

    # Testing
    has_tests: bool = False
    test_framework: str = ""
    test_dirs: list[str] = field(default_factory=list)
    test_file_count: int = 0

    # CI/CD
    has_ci: bool = False
    ci_platform: str = ""
    ci_files: list[str] = field(default_factory=list)

    # Infrastructure
    has_docker: bool = False
    docker_files: list[str] = field(default_factory=list)
    has_k8s: bool = False

    # Documentation
    has_readme: bool = False
    readme_excerpt: str = ""
    has_contributing: bool = False
    has_changelog: bool = False
    has_license: bool = False
    license_type: str = ""

    # Git metadata
    recent_commits: list[dict[str, str]] = field(default_factory=list)
    contributors: list[dict[str, Any]] = field(default_factory=list)
    commit_count: int = 0
    first_commit_date: str = ""
    last_commit_date: str = ""

    # Code patterns
    patterns: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)

    # Key files content (for model context)
    key_file_contents: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}

    def summary_for_prompt(self) -> str:
        """Generate a concise summary suitable for LLM prompt context."""
        lines = []
        lines.append(f"Repository: {self.name}")
        if self.description:
            lines.append(f"Description: {self.description}")
        lines.append(f"Files: {self.total_files}, Directories: {self.total_dirs}")

        if self.languages:
            lang_str = ", ".join(f"{k} ({v:.0f}%)" for k, v in sorted(self.languages.items(), key=lambda x: -x[1])[:8])
            lines.append(f"Languages: {lang_str}")

        if self.frameworks:
            lines.append(f"Frameworks: {', '.join(self.frameworks)}")

        if self.top_dirs:
            dirs = sorted(self.top_dirs.items(), key=lambda x: -x[1])[:12]
            lines.append(f"Top directories: {', '.join(f'{d}/ ({c} files)' for d, c in dirs)}")

        if self.dependencies:
            for cat, deps in self.dependencies.items():
                if deps:
                    lines.append(f"{cat} deps: {', '.join(deps[:15])}")

        if self.has_tests:
            lines.append(f"Testing: {self.test_framework or 'detected'}, {self.test_file_count} test files in {', '.join(self.test_dirs) or 'various dirs'}")

        if self.has_ci:
            lines.append(f"CI/CD: {self.ci_platform}, files: {', '.join(self.ci_files)}")

        if self.has_docker:
            lines.append(f"Docker: {', '.join(self.docker_files)}")
        if self.has_k8s:
            lines.append("Kubernetes: manifests detected")

        if self.patterns:
            lines.append(f"Patterns: {', '.join(self.patterns)}")

        if self.entry_points:
            lines.append(f"Entry points: {', '.join(self.entry_points)}")

        if self.config_files:
            lines.append(f"Config files: {', '.join(self.config_files)}")

        if self.commit_count:
            lines.append(f"Commits: {self.commit_count}, active {self.first_commit_date} to {self.last_commit_date}")

        if self.contributors:
            contribs = ", ".join(f"{c['name']} ({c['commits']})" for c in self.contributors[:8])
            lines.append(f"Contributors: {contribs}")

        return "\n".join(lines)


# --- File tree patterns ---

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", "build", "dist", ".next", ".nuxt", ".output",
    "vendor", "Pods", ".build", ".swiftpm", "DerivedData",
    "coverage", ".coverage", "htmlcov", ".nyc_output",
    ".idea", ".vscode", ".vs", ".gradle", ".settings",
}

IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".class", ".o", ".obj", ".a", ".lib",
    ".so", ".dylib", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar",
    ".lock",  # keep lock files in count but not in analysis
}

# Framework detection from manifest files
FRAMEWORK_DETECTORS = {
    "package.json": "_detect_node_frameworks",
    "Cargo.toml": "_detect_rust_frameworks",
    "go.mod": "_detect_go_frameworks",
    "pyproject.toml": "_detect_python_frameworks",
    "setup.py": "_detect_python_frameworks",
    "requirements.txt": "_detect_python_frameworks",
    "Gemfile": "_detect_ruby_frameworks",
    "pom.xml": "_detect_java_frameworks",
    "build.gradle": "_detect_java_frameworks",
    "build.gradle.kts": "_detect_java_frameworks",
    "Package.swift": "_detect_swift_frameworks",
    "composer.json": "_detect_php_frameworks",
}


def analyze_repo(path: str | Path) -> RepoAnalysis:
    """Run full heuristic analysis on a local repository."""
    path = Path(path).resolve()
    if not path.is_dir():
        raise ValueError(f"Not a directory: {path}")

    name = path.name
    analysis = RepoAnalysis(path=str(path), name=name)

    # Walk the file tree
    _scan_file_tree(path, analysis)

    # Detect languages from extensions
    _detect_languages(analysis)

    # Read and parse manifest files
    _parse_manifests(path, analysis)

    # Detect patterns from structure
    _detect_patterns(path, analysis)

    # Read key files for context
    _read_key_files(path, analysis)

    # Git metadata
    _extract_git_metadata(path, analysis)

    return analysis


def _scan_file_tree(root: Path, analysis: RepoAnalysis) -> None:
    """Walk file tree, count files, extensions, directories."""
    top_dirs: Counter = Counter()
    extensions: Counter = Counter()
    test_dirs = set()
    ci_files = []
    docker_files = []
    config_files = []
    entry_points = []
    total_files = 0
    total_dirs = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        rel = os.path.relpath(dirpath, root)
        if rel == ".":
            total_dirs += len(dirnames)
        else:
            total_dirs += 1

        # Count files under top-level dirs
        parts = Path(rel).parts
        if parts and parts[0] != ".":
            top_dirs[parts[0]] += len(filenames)

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            rel_file = os.path.relpath(fpath, root)
            ext = os.path.splitext(fname)[1].lower()

            if ext in IGNORE_EXTENSIONS:
                continue

            total_files += 1
            if ext:
                extensions[ext] += 1

            # Test detection
            lower = fname.lower()
            lower_rel = rel_file.lower()
            if (
                re.search(r"(^test_|_test\.|\.test\.|\.spec\.|_spec\.)", lower)
                or re.match(r"^(test|tests|__tests__|spec|specs)/", lower_rel)
            ):
                analysis.has_tests = True
                if parts and parts[0] not in (".", "src"):
                    test_dirs.add(parts[0])

            # Test framework detection
            if lower in ("jest.config.js", "jest.config.ts", "jest.config.mjs"):
                analysis.test_framework = "Jest"
            elif lower in ("vitest.config.ts", "vitest.config.js", "vitest.config.mts"):
                analysis.test_framework = "Vitest"
            elif lower in ("pytest.ini", "conftest.py", "tox.ini"):
                analysis.test_framework = analysis.test_framework or "pytest"
            elif lower in ("phpunit.xml", "phpunit.xml.dist"):
                analysis.test_framework = "PHPUnit"
            elif lower == ".rspec":
                analysis.test_framework = "RSpec"

            # CI detection
            if re.match(r"^\.github/workflows/", rel_file):
                analysis.has_ci = True
                analysis.ci_platform = "GitHub Actions"
                ci_files.append(rel_file)
            elif lower in (".travis.yml", ".travis.yaml"):
                analysis.has_ci = True
                analysis.ci_platform = analysis.ci_platform or "Travis CI"
                ci_files.append(rel_file)
            elif lower in ("Jenkinsfile", "jenkins.yml"):
                analysis.has_ci = True
                analysis.ci_platform = analysis.ci_platform or "Jenkins"
                ci_files.append(rel_file)
            elif lower in (".gitlab-ci.yml",):
                analysis.has_ci = True
                analysis.ci_platform = analysis.ci_platform or "GitLab CI"
                ci_files.append(rel_file)
            elif lower in ("azure-pipelines.yml",):
                analysis.has_ci = True
                analysis.ci_platform = analysis.ci_platform or "Azure Pipelines"
                ci_files.append(rel_file)

            # Docker
            if re.match(r"dockerfile", lower) or lower in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                analysis.has_docker = True
                docker_files.append(rel_file)

            # K8s
            if re.match(r".*\.(yaml|yml)$", lower) and any(
                kw in lower for kw in ("k8s", "kubernetes", "deploy", "service", "ingress", "helm")
            ):
                analysis.has_k8s = True

            # Documentation
            if lower == "readme.md" and rel == ".":
                analysis.has_readme = True
            elif lower == "contributing.md":
                analysis.has_contributing = True
            elif lower in ("changelog.md", "changes.md", "history.md"):
                analysis.has_changelog = True
            elif lower == "license" or lower.startswith("license."):
                analysis.has_license = True

            # Config files
            if lower in (
                "tsconfig.json", ".eslintrc.json", ".eslintrc.js", "eslint.config.js",
                "prettier.config.js", ".prettierrc", "babel.config.js",
                "webpack.config.js", "rollup.config.js", "vite.config.ts",
                "next.config.js", "next.config.mjs", "next.config.ts",
                "tailwind.config.js", "tailwind.config.ts",
                "rustfmt.toml", "clippy.toml", ".golangci.yml",
                "mypy.ini", "ruff.toml", "pyrightconfig.json",
            ):
                config_files.append(rel_file)

            # Entry points
            if lower in ("main.py", "app.py", "server.py", "index.ts", "index.js", "main.go", "main.rs", "lib.rs", "main.swift", "app.swift"):
                entry_points.append(rel_file)

    analysis.total_files = total_files
    analysis.total_dirs = total_dirs
    analysis.top_dirs = dict(top_dirs.most_common(20))
    analysis.file_extensions = dict(extensions.most_common(20))
    analysis.test_dirs = sorted(test_dirs)
    analysis.ci_files = ci_files
    analysis.docker_files = docker_files
    analysis.config_files = config_files
    analysis.entry_points = entry_points
    analysis.test_file_count = sum(1 for ext, cnt in extensions.items()
                                    if ext in (".test.js", ".test.ts", ".spec.js")
                                    for _ in range(cnt))
    # Re-count test files properly
    analysis.test_file_count = _count_test_files(root)


def _count_test_files(root: Path) -> int:
    """Count files matching test patterns."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fname in filenames:
            lower = fname.lower()
            if re.search(r"(^test_|_test\.|\.test\.|\.spec\.|_spec\.)", lower):
                count += 1
    return count


# Extension -> Language mapping
EXT_LANG = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".c": "C", ".h": "C/C++",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#",
    ".scala": "Scala",
    ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".lua": "Lua",
    ".r": "R",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".proto": "Protocol Buffers",
    ".sql": "SQL",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".md": "Markdown",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SCSS", ".less": "LESS",
    ".zig": "Zig",
    ".nim": "Nim",
    ".v": "V",
    ".ml": "OCaml", ".mli": "OCaml",
}


def _detect_languages(analysis: RepoAnalysis) -> None:
    """Detect language percentages from file extensions."""
    lang_counts: Counter = Counter()
    for ext, count in analysis.file_extensions.items():
        lang = EXT_LANG.get(ext)
        if lang:
            lang_counts[lang] += count

    total = sum(lang_counts.values())
    if total > 0:
        analysis.languages = {
            lang: round(count / total * 100, 1)
            for lang, count in lang_counts.most_common(10)
        }


def _parse_manifests(root: Path, analysis: RepoAnalysis) -> None:
    """Parse package manifests for frameworks and dependencies."""
    for manifest, detector_name in FRAMEWORK_DETECTORS.items():
        manifest_path = root / manifest
        if manifest_path.is_file():
            try:
                content = manifest_path.read_text(errors="replace")[:50000]
                detector = globals().get(detector_name)
                if detector:
                    detector(content, analysis)
            except Exception:
                pass

    # License detection
    for f in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        lpath = root / f
        if lpath.is_file():
            try:
                text = lpath.read_text(errors="replace")[:500].lower()
                if "mit" in text:
                    analysis.license_type = "MIT"
                elif "apache" in text:
                    analysis.license_type = "Apache-2.0"
                elif "gpl" in text:
                    if "lesser" in text or "lgpl" in text:
                        analysis.license_type = "LGPL"
                    else:
                        analysis.license_type = "GPL"
                elif "bsd" in text:
                    analysis.license_type = "BSD"
                elif "mpl" in text:
                    analysis.license_type = "MPL-2.0"
                elif "isc" in text:
                    analysis.license_type = "ISC"
            except Exception:
                pass
            break


def _detect_node_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Node.js frameworks from package.json."""
    try:
        pkg = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return

    analysis.package_managers.append("npm/yarn/pnpm")
    if pkg.get("description"):
        analysis.description = analysis.description or pkg["description"]

    all_deps = {}
    for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
        deps = pkg.get(dep_key, {})
        all_deps.update(deps)
        if deps:
            analysis.dependencies[dep_key] = list(deps.keys())

    # Framework detection
    fw_map = {
        "next": "Next.js", "react": "React", "vue": "Vue.js",
        "svelte": "Svelte", "@sveltejs/kit": "SvelteKit",
        "express": "Express", "fastify": "Fastify", "koa": "Koa",
        "nuxt": "Nuxt.js", "@angular/core": "Angular",
        "electron": "Electron", "react-native": "React Native",
        "gatsby": "Gatsby", "remix": "Remix",
        "astro": "Astro", "vite": "Vite",
        "webpack": "Webpack", "rollup": "Rollup", "esbuild": "esbuild",
        "tailwindcss": "Tailwind CSS", "prisma": "Prisma",
        "drizzle-orm": "Drizzle ORM", "typeorm": "TypeORM",
        "jest": "Jest", "vitest": "Vitest", "mocha": "Mocha",
        "playwright": "Playwright", "cypress": "Cypress",
    }
    for dep, fw in fw_map.items():
        if dep in all_deps and fw not in analysis.frameworks:
            analysis.frameworks.append(fw)


def _detect_rust_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Rust crate dependencies from Cargo.toml."""
    analysis.package_managers.append("Cargo")

    # Extract description
    desc_match = re.search(r'^description\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if desc_match:
        analysis.description = analysis.description or desc_match.group(1)

    # Extract deps
    deps = re.findall(r'^(\w[\w-]*)\s*=', content, re.MULTILINE)
    crate_fw = {
        "actix-web": "Actix Web", "axum": "Axum", "rocket": "Rocket",
        "tokio": "Tokio", "async-std": "async-std",
        "serde": "Serde", "diesel": "Diesel", "sqlx": "SQLx",
        "tonic": "Tonic (gRPC)", "warp": "Warp",
        "bevy": "Bevy", "clap": "Clap",
        "tracing": "Tracing", "tower": "Tower",
    }
    for dep in deps:
        if dep in crate_fw and crate_fw[dep] not in analysis.frameworks:
            analysis.frameworks.append(crate_fw[dep])

    analysis.dependencies["crates"] = [d for d in deps if d not in ("name", "version", "edition", "description", "authors", "license")]


def _detect_go_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Go module dependencies."""
    analysis.package_managers.append("Go modules")

    deps = re.findall(r'^\t([\w./\-]+)\s', content, re.MULTILINE)
    go_fw = {
        "github.com/gin-gonic/gin": "Gin",
        "github.com/labstack/echo": "Echo",
        "github.com/gofiber/fiber": "Fiber",
        "github.com/gorilla/mux": "Gorilla Mux",
        "google.golang.org/grpc": "gRPC",
        "github.com/spf13/cobra": "Cobra",
        "github.com/urfave/cli": "urfave/cli",
        "gorm.io/gorm": "GORM",
        "github.com/stretchr/testify": "Testify",
    }
    for dep in deps:
        for pattern, fw in go_fw.items():
            if dep.startswith(pattern) and fw not in analysis.frameworks:
                analysis.frameworks.append(fw)

    analysis.dependencies["go_modules"] = deps[:20]


def _detect_python_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Python frameworks."""
    if "package_managers" not in [pm for pm in analysis.package_managers if "pip" in pm]:
        analysis.package_managers.append("pip")

    # Try pyproject.toml format
    py_fw = {
        "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
        "starlette": "Starlette", "tornado": "Tornado",
        "celery": "Celery", "sqlalchemy": "SQLAlchemy",
        "pydantic": "Pydantic", "pytest": "pytest",
        "numpy": "NumPy", "pandas": "pandas",
        "scikit-learn": "scikit-learn", "torch": "PyTorch",
        "tensorflow": "TensorFlow", "transformers": "Transformers",
        "click": "Click", "typer": "Typer",
        "httpx": "HTTPX", "aiohttp": "aiohttp",
        "rich": "Rich", "uvicorn": "Uvicorn",
    }

    found_deps = []
    # pyproject.toml dependencies
    for line in content.split("\n"):
        line = line.strip().strip('"').strip("'").strip(",")
        lower = line.lower()
        for pkg, fw in py_fw.items():
            if lower.startswith(pkg) and fw not in analysis.frameworks:
                analysis.frameworks.append(fw)
                found_deps.append(pkg)
        # requirements.txt style
        match = re.match(r'^([a-zA-Z0-9_-]+)', line)
        if match:
            found_deps.append(match.group(1))

    if found_deps:
        analysis.dependencies["python"] = list(set(found_deps))[:20]


def _detect_ruby_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Ruby frameworks from Gemfile."""
    analysis.package_managers.append("Bundler")
    gems = re.findall(r"gem\s+['\"]([^'\"]+)['\"]", content)
    ruby_fw = {
        "rails": "Ruby on Rails", "sinatra": "Sinatra",
        "rspec": "RSpec", "sidekiq": "Sidekiq",
    }
    for gem in gems:
        if gem in ruby_fw and ruby_fw[gem] not in analysis.frameworks:
            analysis.frameworks.append(ruby_fw[gem])
    analysis.dependencies["gems"] = gems[:20]


def _detect_java_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Java/JVM frameworks."""
    analysis.package_managers.append("Maven/Gradle")
    java_patterns = {
        "spring-boot": "Spring Boot", "spring-framework": "Spring",
        "quarkus": "Quarkus", "micronaut": "Micronaut",
        "junit": "JUnit", "mockito": "Mockito",
    }
    lower = content.lower()
    for pattern, fw in java_patterns.items():
        if pattern in lower and fw not in analysis.frameworks:
            analysis.frameworks.append(fw)


def _detect_swift_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect Swift frameworks from Package.swift."""
    analysis.package_managers.append("Swift Package Manager")
    swift_deps = re.findall(r'\.package\(.*?url:\s*"([^"]+)"', content)
    for dep in swift_deps:
        name = dep.rstrip("/").split("/")[-1].replace(".git", "")
        if name not in analysis.frameworks:
            analysis.frameworks.append(name)


def _detect_php_frameworks(content: str, analysis: RepoAnalysis) -> None:
    """Detect PHP frameworks from composer.json."""
    analysis.package_managers.append("Composer")
    try:
        pkg = json.loads(content)
        deps = list(pkg.get("require", {}).keys()) + list(pkg.get("require-dev", {}).keys())
        php_fw = {
            "laravel/framework": "Laravel", "symfony/framework-bundle": "Symfony",
            "slim/slim": "Slim", "phpunit/phpunit": "PHPUnit",
        }
        for dep in deps:
            if dep in php_fw and php_fw[dep] not in analysis.frameworks:
                analysis.frameworks.append(php_fw[dep])
        analysis.dependencies["composer"] = [d for d in deps if not d.startswith("php")][:20]
    except (json.JSONDecodeError, ValueError):
        pass


def _detect_patterns(root: Path, analysis: RepoAnalysis) -> None:
    """Detect architectural and design patterns from structure."""
    dirs = set(analysis.top_dirs.keys())
    patterns = []

    # Web app patterns
    if {"src", "public"} <= dirs or {"app", "public"} <= dirs:
        patterns.append("Web application")
    if "pages" in dirs or "app" in dirs:
        if "Next.js" in analysis.frameworks:
            patterns.append("Server-side rendering (SSR)")
    if "api" in dirs or "routes" in dirs:
        patterns.append("REST API")
    if "middleware" in dirs:
        patterns.append("Middleware pattern")
    if "components" in dirs:
        patterns.append("Component-based architecture")

    # Backend patterns
    if "models" in dirs or "schemas" in dirs or "entities" in dirs:
        patterns.append("Model layer")
    if "controllers" in dirs or "handlers" in dirs:
        patterns.append("MVC / Handler pattern")
    if "services" in dirs:
        patterns.append("Service layer")
    if "repositories" in dirs or "repos" in dirs:
        patterns.append("Repository pattern")
    if {"domain", "application", "infrastructure"} <= dirs or {"domain", "ports", "adapters"} <= dirs:
        patterns.append("Hexagonal / Clean architecture")
    if "cmd" in dirs:
        patterns.append("Go cmd pattern (multi-binary)")
    if "internal" in dirs or "pkg" in dirs:
        patterns.append("Go project layout")
    if "crates" in dirs or "workspace" in analysis.description.lower():
        patterns.append("Rust workspace (multi-crate)")
    if "proto" in dirs or "protos" in dirs or ".proto" in analysis.file_extensions:
        patterns.append("Protocol Buffers / gRPC")
    if "migrations" in dirs:
        patterns.append("Database migrations")

    # Monorepo patterns
    if "packages" in dirs or "apps" in dirs:
        patterns.append("Monorepo")
    if "lerna.json" in [f.split("/")[-1] for f in analysis.config_files]:
        patterns.append("Lerna monorepo")

    # Plugin / extension patterns
    if "plugins" in dirs or "extensions" in dirs:
        patterns.append("Plugin architecture")

    # Documentation
    if "docs" in dirs or "documentation" in dirs:
        patterns.append("Documentation site")
    if "examples" in dirs or "samples" in dirs:
        patterns.append("Example/sample code included")

    analysis.patterns = patterns


def _read_key_files(root: Path, analysis: RepoAnalysis) -> None:
    """Read content of key files for model context."""
    key_files = [
        "README.md", "CONTRIBUTING.md", "ARCHITECTURE.md",
        "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
    ]
    for fname in key_files:
        fpath = root / fname
        if fpath.is_file():
            try:
                content = fpath.read_text(errors="replace")
                # Limit size for prompt context
                analysis.key_file_contents[fname] = content[:8000]
                if fname == "README.md":
                    analysis.readme_excerpt = content[:2000]
            except Exception:
                pass


def _extract_git_metadata(root: Path, analysis: RepoAnalysis) -> None:
    """Extract git log metadata if available."""
    if not (root / ".git").is_dir():
        return

    try:
        # Recent commits
        result = subprocess.run(
            ["git", "log", "--oneline", "--no-decorate", "-30", "--format=%H|%an|%ad|%s", "--date=short"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    analysis.recent_commits.append({
                        "hash": parts[0][:8],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3][:120],
                    })

        # Commit count
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            analysis.commit_count = int(result.stdout.strip())

        # Date range
        result = subprocess.run(
            ["git", "log", "--reverse", "--format=%ad", "--date=short", "-1"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            analysis.first_commit_date = result.stdout.strip()

        if analysis.recent_commits:
            analysis.last_commit_date = analysis.recent_commits[0].get("date", "")

        # Contributors (top by commit count)
        result = subprocess.run(
            ["git", "shortlog", "-sn", "--no-merges", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n")[:10]:
                match = re.match(r"\s*(\d+)\s+(.*)", line)
                if match:
                    analysis.contributors.append({
                        "name": match.group(2).strip(),
                        "commits": int(match.group(1)),
                    })

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
