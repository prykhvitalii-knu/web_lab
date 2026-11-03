import os
import subprocess
import sys


def test_app_import_does_not_require_mcp_sdk(tmp_path):
    database_path = tmp_path / "lambda-import.sqlite"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database_path}",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "lambda-import-test-secret-key-at-least-32-chars",
    }
    environment.pop("MCP_AGENT_ENABLED", None)
    script = """
import importlib.abc
import sys

class NoMcpSdk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mcp" or fullname.startswith("mcp."):
            raise ModuleNotFoundError("MCP SDK is unavailable in Lambda")

sys.meta_path.insert(0, NoMcpSdk())
import app.main
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
