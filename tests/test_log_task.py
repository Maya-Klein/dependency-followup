"""Tests for .claude/hooks/log_task.py error handling (paths are redirected to tmp_path; the real log is never touched)."""
import importlib.util
import json
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "log_task.py"
spec = importlib.util.spec_from_file_location("log_task", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "LOG", tmp_path / "log.md")
    monkeypatch.setattr(hook, "ERROR_LOG", tmp_path / "data" / "hook_errors.log")
    return tmp_path


def boom():
    raise RuntimeError("simulated failure")


def test_error_is_logged_and_user_is_alerted(paths, monkeypatch, capsys):
    monkeypatch.setattr(hook, "main", boom)
    assert hook.safe_main() == 0
    out = json.loads(capsys.readouterr().out)
    assert "hook_errors.log" in out["systemMessage"]
    text = (paths / "data" / "hook_errors.log").read_text(encoding="utf-8")
    assert "Traceback" in text and "RuntimeError: simulated failure" in text
    assert text.startswith("[20")  # timestamp


def test_failure_to_write_error_log_does_not_raise(paths, monkeypatch, capsys):
    (paths / "data" / "hook_errors.log").mkdir(parents=True)  # a directory: cannot be opened as a file
    monkeypatch.setattr(hook, "main", boom)
    assert hook.safe_main() == 0
    out = json.loads(capsys.readouterr().out)
    assert "נכשלה" in out["systemMessage"]


def test_success_is_silent(paths, monkeypatch, capsys):
    monkeypatch.setattr(hook, "main", lambda: None)
    assert hook.safe_main() == 0
    assert capsys.readouterr().out == ""
    assert not (paths / "data" / "hook_errors.log").exists()
