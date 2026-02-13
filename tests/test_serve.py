"""Tests for the serve module."""

import json
import threading
import time
from urllib.request import urlopen

import pytest

from engram_cli.serve import _load_analysis_data, start_server


@pytest.fixture
def sample_output(tmp_path):
    """Create a sample engram output directory."""
    data = {
        "analysis": {"name": "test-repo", "total_files": 10},
        "skills": [
            {
                "org": "test-org",
                "repo": "test-repo",
                "tier": 2,
                "path": "architecture/SKILL.md",
                "name": "architecture.md",
                "content": "---\nname: test\n---\n# Architecture\nTest content",
            }
        ],
        "memories": [
            {
                "org": "test-org",
                "repo": ".memory",
                "path": "sessions/2026-02-13-test.md",
                "name": "test.md",
                "content": "---\ndate: 2026-02-13\n---\n# Session\nTest memory",
            }
        ],
        "model_used": "test-model",
        "generation_time_seconds": 1.5,
        "errors": [],
    }
    (tmp_path / "engram-analysis.json").write_text(json.dumps(data))
    return tmp_path


class TestLoadAnalysisData:
    def test_load_from_json(self, sample_output):
        data = _load_analysis_data(sample_output)
        assert len(data["skills"]) == 1
        assert len(data["memories"]) == 1
        assert data["model_used"] == "test-model"

    def test_load_from_subdirs(self, tmp_path):
        sub = tmp_path / "my-repo"
        sub.mkdir()
        data = {
            "skills": [
                {
                    "org": "a",
                    "repo": "b",
                    "path": "x",
                    "name": "y",
                    "content": "z",
                    "tier": 2,
                }
            ],
            "memories": [],
        }
        (sub / "engram-analysis.json").write_text(json.dumps(data))
        result = _load_analysis_data(tmp_path)
        assert len(result["skills"]) == 1

    def test_load_nonexistent(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            _load_analysis_data(empty)


class TestServer:
    def test_serve_and_api(self, sample_output):
        port = 18421
        server_thread = threading.Thread(
            target=start_server,
            args=(sample_output,),
            kwargs={"port": port, "open_browser": False},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.5)

        try:
            # Test viewer endpoint
            resp = urlopen(f"http://localhost:{port}/")
            html = resp.read().decode()
            assert "<title>" in html
            assert "Engram" in html

            # Test API endpoint
            resp = urlopen(f"http://localhost:{port}/api/data")
            data = json.loads(resp.read().decode())
            assert len(data["skills"]) == 1
            assert len(data["memories"]) == 1
            assert data["model_used"] == "test-model"
        finally:
            pass  # daemon thread will be cleaned up
