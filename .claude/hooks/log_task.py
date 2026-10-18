"""Stop hook: append a short entry to the project's work log in the Obsidian vault.

Reads the hook payload (JSON) from stdin. Never fails the session: any error is swallowed.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path(r"C:\Users\user\Dev\AI_Developers\Notes\dependency-followup\יומן עבודה.md")
HEADER = "# יומן עבודה\n\nרשומות אוטומטיות מ-hook של Claude Code, בסוף כל סבב. הסיכום הוא ההודעה האחרונה של Claude.\n"
MAX_CHARS = 600


def last_assistant_text(transcript_path):
    last = ""
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") != "assistant":
                continue
            content = obj.get("message", {}).get("content", [])
            if isinstance(content, str):
                text = content
            else:
                text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
            if text.strip():
                last = text.strip()
    return last


def git(cwd, *args):
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def main():
    payload = json.load(sys.stdin)
    cwd = payload.get("cwd") or "."
    summary = ""
    if payload.get("transcript_path"):
        summary = last_assistant_text(payload["transcript_path"])
    if not summary:
        return
    summary = " ".join(summary.split())
    if len(summary) > MAX_CHARS:
        summary = summary[:MAX_CHARS].rstrip() + "…"

    lines = [f"\n## {datetime.now():%Y-%m-%d %H:%M}"]
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    commit = git(cwd, "log", "-1", "--format=%h %s")
    if branch:
        lines.append(f"- ענף: {branch}" + (f" · commit אחרון: {commit}" if commit else ""))
    lines.append(f"- סיכום: {summary}")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.write_text(HEADER, encoding="utf-8")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
