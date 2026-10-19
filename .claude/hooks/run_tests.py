"""Stop hook: run the full pytest suite when code files (py, html, css) changed since the last green run.

Docs-only changes are skipped. On failure it prints the pytest output to stderr and exits 2,
which blocks the stop and feeds the failure back to Claude. The last green state is kept in
data/.last_tested (git-ignored).
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / "data" / ".last_tested"
CODE_SUFFIXES = {".py", ".html", ".css"}
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


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
    if result.returncode == 0:
        STAMP.parent.mkdir(exist_ok=True)
        STAMP.write_text(fingerprint)
        return 0
    sys.stderr.write("pytest failed. Fix the failing tests before continuing.\n\n")
    sys.stderr.write((result.stdout + result.stderr)[-4000:])
    return 2


if __name__ == "__main__":
    sys.exit(main())
