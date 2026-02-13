"""Tests for the heuristic analyzer."""

import pytest

from engram_cli.analyzer import analyze_repo


@pytest.fixture
def sample_python_repo(tmp_path):
    """Create a sample Python repo structure."""
    # Root files
    (tmp_path / "README.md").write_text("# My Project\nA cool project\n")
    (tmp_path / "LICENSE").write_text("MIT License\nCopyright 2026")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "myproject"\ndescription = "A cool project"\n'
        'dependencies = [\n  "fastapi>=0.100",\n  "pydantic>=2.0",\n  "sqlalchemy>=2.0",\n]\n'
        '\n[project.optional-dependencies]\ndev = ["pytest>=8.0", "ruff>=0.1"]\n'
    )

    # Source
    src = tmp_path / "src" / "myproject"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("__version__ = '1.0.0'")
    (src / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    (src / "models.py").write_text("from sqlalchemy import Column\nclass User: pass\n")
    (src / "routes.py").write_text(
        "from . import app\n@app.get('/')\ndef root(): pass\n"
    )
    (src / "services.py").write_text("class UserService: pass\n")

    # Tests
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "conftest.py").write_text("import pytest\n")
    (tests / "test_main.py").write_text("def test_root(): pass\n")
    (tests / "test_models.py").write_text("def test_user(): pass\n")

    # CI
    ci = tmp_path / ".github" / "workflows"
    ci.mkdir(parents=True)
    (ci / "ci.yml").write_text("name: CI\non: push\n")

    # Docker
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    build: .\n")

    # Docs
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Docs\n")

    return tmp_path


@pytest.fixture
def sample_rust_repo(tmp_path):
    """Create a sample Rust repo structure."""
    (tmp_path / "README.md").write_text("# RustDB\nA key-value store\n")
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "rustdb"\nversion = "0.1.0"\nedition = "2021"\n'
        'description = "A fast key-value store"\n\n'
        '[dependencies]\ntokio = { version = "1", features = ["full"] }\n'
        'tonic = "0.11"\nserde = { version = "1", features = ["derive"] }\n'
        'tracing = "0.1"\n'
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.rs").write_text('fn main() { println!("hello"); }\n')
    (src / "lib.rs").write_text("pub mod storage;\npub mod server;\n")
    (src / "storage.rs").write_text("pub struct Store {}\n")
    (src / "server.rs").write_text("pub struct Server {}\n")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "integration_test.rs").write_text("#[test]\nfn test_store() {}\n")

    proto = tmp_path / "proto"
    proto.mkdir()
    (proto / "api.proto").write_text('syntax = "proto3";\n')

    ci = tmp_path / ".github" / "workflows"
    ci.mkdir(parents=True)
    (ci / "ci.yml").write_text("name: CI\non: push\n")
    (ci / "release.yml").write_text("name: Release\non: tag\n")

    return tmp_path


@pytest.fixture
def sample_node_repo(tmp_path):
    """Create a sample Node.js/Next.js repo structure."""
    (tmp_path / "README.md").write_text("# WebApp\nNext.js web application\n")
    (tmp_path / "package.json").write_text(
        '{"name": "webapp", "description": "A web app", '
        '"dependencies": {"next": "^14", "react": "^18", "react-dom": "^18", '
        '"tailwindcss": "^3", "drizzle-orm": "^0.30"}, '
        '"devDependencies": {"vitest": "^1", "typescript": "^5", "playwright": "^1"}}'
    )
    (tmp_path / "next.config.js").write_text("module.exports = {}\n")
    (tmp_path / "tailwind.config.js").write_text("module.exports = {}\n")
    (tmp_path / "tsconfig.json").write_text("{}\n")

    app = tmp_path / "app"
    app.mkdir()
    (app / "page.tsx").write_text("export default function Home() {}\n")
    (app / "layout.tsx").write_text("export default function Layout() {}\n")

    api = app / "api" / "users"
    api.mkdir(parents=True)
    (api / "route.ts").write_text("export async function GET() {}\n")

    components = tmp_path / "components"
    components.mkdir()
    (components / "Header.tsx").write_text("export default function Header() {}\n")
    (components / "Header.test.tsx").write_text("test('renders', () => {})\n")

    return tmp_path


class TestAnalyzeRepo:
    """Test full repo analysis."""

    def test_python_repo(self, sample_python_repo):
        analysis = analyze_repo(sample_python_repo)
        assert analysis.name == sample_python_repo.name
        assert analysis.total_files > 0
        assert "Python" in analysis.languages
        assert analysis.has_tests
        assert analysis.test_framework == "pytest"
        assert analysis.has_ci
        assert analysis.ci_platform == "GitHub Actions"
        assert analysis.has_docker
        assert analysis.has_readme
        assert analysis.has_license
        assert analysis.license_type == "MIT"
        assert "FastAPI" in analysis.frameworks
        assert "Pydantic" in analysis.frameworks
        assert "SQLAlchemy" in analysis.frameworks
        assert len(analysis.ci_files) >= 1
        assert len(analysis.docker_files) >= 1
        assert any(
            "Web application" in p or "Documentation" in p for p in analysis.patterns
        )

    def test_rust_repo(self, sample_rust_repo):
        analysis = analyze_repo(sample_rust_repo)
        assert "Rust" in analysis.languages
        assert "Cargo" in analysis.package_managers
        assert "Tokio" in analysis.frameworks
        assert "Tonic (gRPC)" in analysis.frameworks
        assert analysis.has_tests
        assert analysis.has_ci
        assert len(analysis.ci_files) == 2
        assert "Protocol Buffers / gRPC" in analysis.patterns
        assert analysis.description == "A fast key-value store"

    def test_node_repo(self, sample_node_repo):
        analysis = analyze_repo(sample_node_repo)
        assert "TypeScript" in analysis.languages or "JavaScript" in analysis.languages
        assert "Next.js" in analysis.frameworks
        assert "React" in analysis.frameworks
        assert "Tailwind CSS" in analysis.frameworks
        assert "Drizzle ORM" in analysis.frameworks
        assert "Vitest" in analysis.frameworks
        assert analysis.has_tests
        assert analysis.description == "A web app"

    def test_empty_repo(self, tmp_path):
        analysis = analyze_repo(tmp_path)
        assert analysis.total_files == 0
        assert not analysis.has_tests
        assert not analysis.has_ci
        assert len(analysis.languages) == 0

    def test_nonexistent_path(self):
        with pytest.raises(ValueError, match="Not a directory"):
            analyze_repo("/nonexistent/path")


class TestRepoAnalysis:
    """Test RepoAnalysis methods."""

    def test_summary_for_prompt(self, sample_python_repo):
        analysis = analyze_repo(sample_python_repo)
        summary = analysis.summary_for_prompt()
        assert "Repository:" in summary
        assert "Languages:" in summary
        assert "Python" in summary
        assert "Frameworks:" in summary
        assert "FastAPI" in summary

    def test_to_dict(self, sample_python_repo):
        analysis = analyze_repo(sample_python_repo)
        d = analysis.to_dict()
        assert isinstance(d, dict)
        assert "name" in d
        assert "languages" in d
        assert "frameworks" in d

    def test_key_files_read(self, sample_python_repo):
        analysis = analyze_repo(sample_python_repo)
        assert "README.md" in analysis.key_file_contents
        assert "pyproject.toml" in analysis.key_file_contents
        assert "cool project" in analysis.readme_excerpt
