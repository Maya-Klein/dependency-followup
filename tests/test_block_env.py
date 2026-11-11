"""Tests for .claude/hooks/block_env.py (the strings are only fed to check(); nothing is executed or read)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "block_env.py"
spec = importlib.util.spec_from_file_location("block_env", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

BLOCKED = [
    ("Read", {"file_path": "C:\\Users\\user\\proj\\.env"}),
    ("Read", {"file_path": "/home/u/proj/.env"}),
    ("Read", {"file_path": ".env.local"}),
    ("Read", {"file_path": "C:\\proj\\.ENV"}),
    ("Edit", {"file_path": ".env", "old_string": "a", "new_string": "b"}),
    ("Write", {"file_path": "proj/.env", "content": "x"}),
    ("Grep", {"pattern": "KEY", "path": ".env"}),
    ("Grep", {"pattern": "KEY", "glob": ".env*"}),
    ("Glob", {"pattern": "**/.env"}),
    ("Bash", {"command": "cat .env"}),
    ("Bash", {"command": "cat ./.env"}),
    ("Bash", {"command": "head -n 3 /proj/.env.local"}),
    ("Bash", {"command": "echo X=1 >> .env"}),
    ("Bash", {"command": "python -c \"print(open('.env').read())\""}),
    ("PowerShell", {"command": "Get-Content .env"}),
    ("PowerShell", {"command": "type .\\.env"}),
    ("PowerShell", {"command": "gc C:\\proj\\.env | Select -First 2"}),
    ("PowerShell", {"command": "cp .env.example .env"}),
]
ALLOWED = [
    ("Read", {"file_path": "C:\\proj\\.env.example"}),
    ("Read", {"file_path": "docs/plan.md"}),
    ("Edit", {"file_path": "app/web/routes.py", "old_string": "a", "new_string": "b"}),
    ("Write", {"file_path": "scripts/environment.py", "content": "x"}),
    ("Grep", {"pattern": "\\.env", "path": "app"}),
    ("Grep", {"pattern": "dotenv", "glob": "*.py"}),
    ("Glob", {"pattern": "**/*.py"}),
    ("Bash", {"command": "cat .env.example"}),
    ("Bash", {"command": "ls .venv/Scripts"}),
    ("Bash", {"command": ".venv\\Scripts\\python -m pytest"}),
    ("Bash", {"command": "python -c \"import os; print(os.environ.get('HOME'))\""}),
    ("Bash", {"command": "git status"}),
    ("PowerShell", {"command": "Get-ChildItem Env:"}),
    ("PowerShell", {"command": "$env:PATH"}),
    ("PowerShell", {"command": "pip install python-dotenv"}),
]


@pytest.mark.parametrize("tool,tool_input", BLOCKED)
def test_blocked(tool, tool_input):
    assert hook.check(tool, tool_input) is True


@pytest.mark.parametrize("tool,tool_input", ALLOWED)
def test_allowed(tool, tool_input):
    assert hook.check(tool, tool_input) is False


@pytest.mark.parametrize("tool_input", [None, "x", 5, {}, {"command": 5}, {"file_path": None}])
def test_odd_input_is_allowed(tool_input):
    assert hook.check("Bash", tool_input) is False
    assert hook.check("Read", tool_input) is False


def run_hook(payload, raw=None):
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=data.encode("utf-8"), capture_output=True)


def test_end_to_end_denies_with_hebrew_reason():
    out = run_hook({"tool_name": "Read", "tool_input": {"file_path": "C:\\proj\\.env"}})
    assert out.returncode == 0
    decision = json.loads(out.stdout.decode("utf-8"))
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert ".env" in decision["systemMessage"]


def test_end_to_end_allows_silently():
    out = run_hook({"tool_name": "Read", "tool_input": {"file_path": "docs/plan.md"}})
    assert out.returncode == 0 and out.stdout == b""


def test_broken_input_never_blocks():
    for raw in ("not json", "", "{}", '{"tool_name": "Bash"}'):
        out = run_hook(None, raw=raw)
        assert out.returncode == 0 and out.stdout == b""
