"""Stop hook: run the full pytest suite when code files (py, html, css) changed since the last green run.

Docs-only changes are skipped. On failure it prints the pytest output to stderr and exits 2,
which blocks the stop and feeds the failure back to Claude. After MAX_FAILURES consecutive
failures it stops blocking and alerts the user (sound, Windows dialog, message, Obsidian log entry).
The last green state is kept in
data/.last_tested and the failure count in data/.test_failures (both git-ignored); a green run
resets the count.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from log_task import HEADER, LOG

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / "data" / ".last_tested"
CODE_SUFFIXES = {".py", ".html", ".css"}
FAILURES = ROOT / "data" / ".test_failures"
MAX_FAILURES = 3
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ALERT = "⚠️ הבדיקות נכשלו 3 פעמים ברצף. קלוד לא הצליח לתקן. כדאי לשאול אותו מה קרה."
DIALOG_PS = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$f = New-Object System.Windows.Forms.Form; $f.TopMost = $true;"
    "[System.Windows.Forms.MessageBox]::Show($f, $env:HOOK_ALERT_TEXT, 'מעקב תלויות - בדיקות נכשלו',"
    " 'OK', 'Warning', 'Button1', 0x180000) | Out-Null"  # RtlReading | RightAlign
)


def read_failures():
    try:
        return int(FAILURES.read_text().strip())
    except (OSError, ValueError):
        return 0


def alert_user(branch):
    """Fire all alerts; each one is best-effort so a failure in one never hides the others."""
    try:
        import winsound
        for freq, ms in ((880, 150), (440, 150), (880, 150), (440, 400)):
            winsound.Beep(freq, ms)  # distinct from the normal completion sound
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", DIALOG_PS],
            env={**os.environ, "HOOK_ALERT_TEXT": ALERT},
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if not LOG.exists():
            LOG.write_text(HEADER, encoding="utf-8")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M}\n- ענף: {branch}\n- {ALERT}\n")
    except Exception:
        pass


def current_branch():
    out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() or "?"


def code_fingerprint():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    digest = hashlib.sha256()
    for name in sorted(set(filter(None, out.split("\0")))):
        path = ROOT / name
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        digest.update(name.encode("utf-8") + b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    fingerprint = code_fingerprint()
    if STAMP.exists() and STAMP.read_text().strip() == fingerprint:
        return 0
    python = str(PYTHON) if PYTHON.exists() else sys.executable
    result = subprocess.run(
        [python, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True,
    )
    STAMP.parent.mkdir(exist_ok=True)
    if result.returncode == 0:
        STAMP.write_text(fingerprint)
        FAILURES.unlink(missing_ok=True)
        return 0
    failures = read_failures() + 1
    FAILURES.write_text(str(failures))
    output = (result.stdout + result.stderr)[-4000:]
    if failures >= MAX_FAILURES:
        if failures == MAX_FAILURES:
            alert_user(current_branch())
        print(json.dumps({"systemMessage": (ALERT + "\n\n" + output)[:1500]}))
        return 0
    sys.stderr.write(f"pytest failed ({failures}/{MAX_FAILURES}). Fix the failing tests before continuing.\n\n")
    sys.stderr.write(output)
    return 2


if __name__ == "__main__":
    sys.exit(main())
