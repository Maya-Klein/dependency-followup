"""Tests for block_dangerous.py. Run: python test_block_dangerous.py

The commands below are only strings that are fed to check(); none of them is ever executed.
Each case: (group, command, tool, expected) where expected is True if it must be blocked.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("block_dangerous", HERE / "block_dangerous.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

B, A = True, False  # blocked, allowed
PS, BASH = "PowerShell", "Bash"

# The 25 original cases of 20.10.2026 were not saved (the journal keeps only the counts, 14 blocked and 11 allowed,
# and three examples). This is a reconstruction of them from the three original rules.
ORIGINAL = [
    ("orig", "rm -rf x", BASH, B), ("orig", "rm -r x", BASH, B), ("orig", "rm -fr x", BASH, B),
    ("orig", "rm --recursive x", BASH, B), ("orig", "Remove-Item -Recurse x", PS, B),
    ("orig", "Remove-Item -Recurse -Force x", PS, B), ("orig", "ri x -Recurse", PS, B),
    ("orig", "rmdir /s /q x", PS, B), ("orig", "rd /s x", PS, B), ("orig", "del /s x", PS, B),
    ("orig", "git push --force", BASH, B), ("orig", "git push -f origin x", BASH, B),
    ("orig", "git push --force-with-lease", BASH, B), ("orig", "DROP TABLE topics", BASH, B),
    ("orig", "rm file.txt", BASH, A), ("orig", "rm -f file.txt", BASH, A), ("orig", "git push -u origin x", BASH, A),
    ("orig", "git push origin main", BASH, A), ("orig", "grep -r foo .", BASH, A), ("orig", "ls -r", BASH, A),
    ("orig", "git status", BASH, A), ("orig", "git commit -m update-docs", BASH, A),
    ("orig", "Remove-Item file.txt", PS, A), ("orig", "rmdir emptydir", PS, A), ("orig", "python -m pytest", BASH, A),
]

FIXED_FALSE_POSITIVES = [  # item 1 of the proposal
    ("recursive", "Remove-Item -Recurse -Force x", PS, B), ("recursive", "Remove-Item x -r", PS, B),
    ("recursive", "ri -Rec x", PS, B), ("recursive", "Remove-Item -Force x", PS, A),
    ("recursive", "Remove-Item -LiteralPath a -Force", PS, A), ("recursive", "Remove-Item -Confirm x", PS, A),
    ("recursive", "Remove-Item -Force x", BASH, A),
    ("recursive", "rm -rf build", BASH, B), ("recursive", "rm -Rf x", BASH, B), ("recursive", "rm --recursive x", BASH, B),
    ("recursive", "rm -f log", BASH, A), ("recursive", "rm --force x", BASH, A),
    ("recursive", "rm -Recurse x", PS, B), ("recursive", "del x -r", PS, B), ("recursive", "rm -Force x", PS, A),
    ("recursive", "del x", PS, A),
    ("recursive", "rd /s /q x", BASH, B), ("recursive", "del /s x", BASH, B), ("recursive", "rd emptydir", BASH, A),
    ("recursive", "rm /srv/x", BASH, A),
    ("recursive", "rm -Force x", None, B),  # tool unknown: the stricter bash reading is used
    ("recursive", "cd x && rm -rf y", BASH, B), ("recursive", "git status && rm file.txt", BASH, A),
]

GAPS = [  # item 2 of the proposal
    ("reset --hard", "git reset --hard HEAD~1", BASH, B), ("reset --hard", "git -C repo reset --hard", BASH, B),
    ("reset --hard", "cd x && git reset --hard", BASH, B),
    ("reset --hard", "git reset --soft HEAD~1", BASH, A), ("reset --hard", "git reset HEAD file.py", BASH, A),
    ("clean", "git clean -fd", BASH, B), ("clean", "git clean -f", BASH, B), ("clean", "git clean -d", BASH, B),
    ("clean", "git clean --force", BASH, B), ("clean", "git clean -fdx", BASH, B), ("clean", "git clean -f -d", BASH, B),
    ("clean", "git clean -n", BASH, A), ("clean", "git clean -nd", BASH, A), ("clean", "git clean -fdn", BASH, A),
    ("clean", "git clean --dry-run", BASH, A), ("clean", "git clean -i", BASH, A),
    ("gci pipe", "Get-ChildItem x -Recurse | Remove-Item -Force", PS, B), ("gci pipe", "gci -r | ri", PS, B),
    ("gci pipe", "Get-ChildItem -Recurse|Remove-Item", PS, B),
    ("gci pipe", "Get-ChildItem -Recurse | Select-Object Name", PS, A), ("gci pipe", "Get-ChildItem x | Remove-Item", PS, A),
    ("find", "find . -name '*.pyc' -delete", BASH, B), ("find", "find . -name '*.pyc'", BASH, A),
    ("find", "find . -name x -print", BASH, A),
    ("rmtree", "python -c \"import shutil; shutil.rmtree('x')\"", BASH, B),
    ("rmtree", "python -c \"import shutil; shutil.copytree('a','b')\"", BASH, A),
    ("rmtree", "python -c \"import os; os.remove('f')\"", BASH, A),
    ("sql", "DROP DATABASE app", BASH, B), ("sql", "drop table topics", BASH, B), ("sql", "DROP INDEX idx", BASH, A),
    ("sql", "git stash drop", BASH, A),
    ("truncate", "TRUNCATE TABLE topics", BASH, B), ("truncate", "truncate topics", BASH, B),
    ("truncate", "TRUNCATE topics;", BASH, B), ("truncate", "truncate -s 0 app.log", BASH, A),
    ("truncate", "echo truncated output", BASH, A),
]

REQUESTED_EXTRA = [  # added on request after the proposal
    ("push +ref", "git push origin +main", BASH, B), ("push +ref", "git push origin +HEAD:main", BASH, B),
    ("push +ref", "git push origin main", BASH, A), ("push +ref", "git push origin a+b", BASH, A),
    ("push +ref", "git push -u origin feature/x", BASH, A), ("push +ref", "git push --delete origin old", BASH, A),
    ("checkout .", "git checkout -- .", BASH, B), ("checkout .", "git checkout .", BASH, B),
    ("checkout .", "git checkout main", BASH, A), ("checkout .", "git checkout -b feature/x", BASH, A),
    ("checkout .", "git checkout -- file.py", BASH, A),
    ("restore .", "git restore .", BASH, B), ("restore .", "git restore --staged --worktree .", BASH, B),
    ("restore .", "git restore --staged .", BASH, A), ("restore .", "git restore file.py", BASH, A),
    ("branch -D", "git branch -D old", BASH, B), ("branch -D", "git branch -df old", BASH, B),
    ("branch -D", "git branch -d old", BASH, A), ("branch -D", "git branch -f main HEAD~1", BASH, A),
    ("branch -D", "git branch --list", BASH, A), ("branch -D", "git branch -m new-name", BASH, A),
]

SECTIONS = [
    ("original (reconstructed)", ORIGINAL),
    ("1. false positives fixed", FIXED_FALSE_POSITIVES),
    ("2. gaps closed", GAPS),
    ("requested extras", REQUESTED_EXTRA),
]


def end_to_end():
    """The real script, fed through stdin like Claude Code does; the command text is only in the stdin data."""
    def run(command, tool):
        payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}})
        out = subprocess.run(
            [sys.executable, str(HERE / "block_dangerous.py")], input=payload.encode("utf-8"), capture_output=True
        )
        return out.returncode, out.stdout.decode("utf-8")

    problems = []
    code, out = run("git push origin +main", "Bash")
    data = json.loads(out) if out else {}
    if code != 0 or data.get("hookSpecificOutput", {}).get("permissionDecision") != "deny":
        problems.append("blocked command did not produce a deny decision")
    if "נחסם" not in data.get("systemMessage", ""):
        problems.append("the Hebrew message is missing")
    code, out = run("git status", "Bash")
    if code != 0 or out.strip():
        problems.append("allowed command produced output")
    # a broken payload must never break the session
    bad = subprocess.run([sys.executable, str(HERE / "block_dangerous.py")], input=b"not json", capture_output=True)
    if bad.returncode != 0 or bad.stdout:
        problems.append("a broken payload was not ignored")
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # the block reasons are Hebrew
    failures = []
    total = 0
    for title, cases in SECTIONS:
        print(f"\n== {title} ({len(cases)}) ==")
        for group, command, tool, expected in cases:
            found = hook.check(command, tool)
            got = found is not None
            total += 1
            mark = "ok  " if got == expected else "FAIL"
            verdict = "BLOCK" if got else "allow"
            reason = f"  [{found[0]}]" if found else ""
            print(f"{mark} {verdict:5} ({tool or 'unknown'}) {command}{reason}")
            if got != expected:
                failures.append((command, tool, expected, got))
    problems = end_to_end()
    for p in problems:
        print("FAIL end-to-end:", p)
    print(f"\n{total - len(failures)}/{total} cases passed, end-to-end: {'ok' if not problems else 'FAILED'}")
    sys.exit(1 if failures or problems else 0)


if __name__ == "__main__":
    main()
