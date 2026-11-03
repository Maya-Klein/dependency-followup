# יש עותק בפרויקט dependency-followup (docs/global-hooks/). כל שינוי כאן צריך להיות מועתק גם לשם.
"""PreToolUse hook (Bash / PowerShell): blocks dangerous commands and explains why in Hebrew.

Blocked:
  - recursive deletion (rm -r, Remove-Item -Recurse, rd /s, ...), also Get-ChildItem -Recurse piped to Remove-Item
  - find ... -delete, shutil.rmtree
  - git: push --force / -f / +branch, reset --hard, clean -f/-d (not a dry run),
    checkout . / restore . (discard all changes), branch -D (delete an unmerged branch)
  - SQL: DROP TABLE, DROP DATABASE, TRUNCATE

Reads the hook JSON from stdin. To block, prints a deny decision as JSON and exits 0.
On any parsing problem it allows the command (never breaks the session).
The check is on the command text only, so text that merely mentions a pattern (a commit message) is blocked too.
"""
import json
import re
import sys

SEG = r"[^;&|\n]*"  # stay inside one command segment
STMT = r"[^;&\n]*"  # stay inside one statement (a pipeline may continue after "|")
# -r or any prefix of -Recurse (PowerShell accepts abbreviations): -r, -re, -rec, ..., -Recurse
PS_RECURSE = r"-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?(?=[\s:]|$)"
# bash: --recursive, or a short-flag cluster that contains r or R (-r, -rf, -Rf, -fr)
BASH_RECURSE = r"(?:--recursive|-[A-Za-z]*[rR][A-Za-z]*)(?=\s|$)"

WHY_RECURSIVE = (
    "הפקודה מוחקת תיקייה ואת כל מה שבתוכה, בלי לשאול ובלי סל מחזור. "
    "אם נתיב נכתב לא נכון, אפשר למחוק בטעות קבצים חשובים (למשל את כל הפרויקט) ואי אפשר לשחזר."
)
WHY_PUSH = (
    "דחיפה בכוח דורסת את ההיסטוריה שנמצאת בשרת (GitHub). "
    "קומיטים שכבר קיימים שם יכולים להימחק, ומי שעובד על אותו ענף יסבול מזה."
)
WHY_SQL = "הפקודה מוחקת טבלה או מסד נתונים שלם יחד עם כל הנתונים שבו, ואי אפשר לשחזר אותם בלי גיבוי."

NAME_RECURSIVE = "מחיקה רקורסיבית של תיקיות"
NAME_PUSH = "git push --force"

# plain text patterns: (name, compiled pattern, explanation)
TEXT_RULES = [
    (
        "מחיקה רקורסיבית דרך Get-ChildItem",
        re.compile(
            r"\b(get-childitem|gci|dir|ls)\b" + STMT + r"\s" + PS_RECURSE.replace("(?=[\\s:]|$)", "(?=[\\s:|]|$)")
            + STMT + r"\|" + STMT + r"\b(remove-item|ri|rm|del|erase)\b",
            re.I,
        ),
        WHY_RECURSIVE,
    ),
    (
        "find עם -delete",
        re.compile(r"\bfind\b" + SEG + r"\s-delete(?=\s|$)"),
        "הפקודה מוחקת את כל הקבצים שנמצאו, בלי לשאול ובלי סל מחזור. אם התנאי רחב מדי, נמחקים קבצים חשובים.",
    ),
    (
        "shutil.rmtree",
        re.compile(r"\bshutil\s*\.\s*rmtree\b|\brmtree\s*\("),
        WHY_RECURSIVE,
    ),
    ("DROP TABLE / DROP DATABASE", re.compile(r"\bdrop\s+(table|database)\b", re.I), WHY_SQL),
    (
        "TRUNCATE",
        re.compile(r"\btruncate\s+table\b|\btruncate\s+[\w.\"`\[\]]+\s*(?:;|$)", re.I),
        "הפקודה מוחקת את כל השורות בטבלה בבת אחת, ואי אפשר לשחזר אותן בלי גיבוי.",
    ),
]

GIT_SUBCOMMANDS = {"push", "reset", "clean", "checkout", "restore", "branch"}
GIT_TOKEN = re.compile(r"(.*[\\/])?git(\.exe)?", re.I)


def recursive_delete(command, tool):
    """rm / Remove-Item and friends with a real recursive flag; the tool decides what a flag means."""
    # Remove-Item / ri is PowerShell in any tool
    if re.search(r"\b(remove-item|ri)\b" + SEG + r"\s" + PS_RECURSE, command, re.I):
        return True
    # cmd.exe style: rd /s, del /s
    if re.search(r"\b(rd|rmdir|del|erase)\b" + SEG + r"\s/s(?=\s|$)", command, re.I):
        return True
    if tool != "Bash":  # PowerShell, or unknown: the aliases take -Recurse (or a prefix of it)
        if re.search(r"\b(rm|rmdir|rd|del|erase)\b" + SEG + r"\s" + PS_RECURSE, command, re.I):
            return True
    if tool != "PowerShell":  # Bash, or unknown: rm takes -r / -R / -rf / --recursive
        if re.search(r"\brm\b" + SEG + r"\s" + BASH_RECURSE, command):
            return True
    return False


def short_letters(args):
    """The letters of all single-dash flags, so -fd, -f -d and -df look the same."""
    return "".join(t[1:] for t in args if re.fullmatch(r"-[A-Za-z]+", t))


def git_danger(command):
    """Returns (name, why) for a dangerous git command in any segment of the command, else None."""
    for segment in re.split(r"[;&|\n]+", command):
        tokens = segment.split()
        git_at = next((i for i, t in enumerate(tokens) if GIT_TOKEN.fullmatch(t)), None)
        if git_at is None:
            continue
        rest = tokens[git_at + 1:]
        sub_at = next((i for i, t in enumerate(rest) if t in GIT_SUBCOMMANDS), None)
        if sub_at is None:
            continue
        sub, args = rest[sub_at], rest[sub_at + 1:]
        short = short_letters(args)
        has = set(args)

        if sub == "push":
            forced = any(t.startswith("--force") for t in args) or "f" in short
            plus_ref = any(t.startswith("+") and len(t) > 1 for t in args)
            if forced or plus_ref:
                return NAME_PUSH, WHY_PUSH
        elif sub == "reset" and "--hard" in has:
            return (
                "git reset --hard",
                "הפקודה מוחקת את כל השינויים שעוד לא נשמרו ב-commit, ואי אפשר לשחזר אותם.",
            )
        elif sub == "clean":
            dry_run = "n" in short or "--dry-run" in has
            if ("f" in short or "d" in short or "--force" in has) and not dry_run:
                return (
                    "git clean",
                    "הפקודה מוחקת קבצים ותיקיות שלא במעקב של git, בלי סל מחזור. "
                    "אפשר לראות קודם מה יימחק עם git clean -n.",
                )
        elif sub == "checkout" and "." in has:
            return (
                "git checkout . (ביטול כל השינויים)",
                "הפקודה מחליפה את הקבצים בתיקייה בגרסה האחרונה שנשמרה, ושינויים שלא נשמרו יימחקו.",
            )
        elif sub == "restore" and "." in has:
            staged_only = ("--staged" in has or "S" in short) and not ("--worktree" in has or "W" in short)
            if not staged_only:
                return (
                    "git restore . (ביטול כל השינויים)",
                    "הפקודה מחליפה את הקבצים בתיקייה בגרסה האחרונה שנשמרה, ושינויים שלא נשמרו יימחקו.",
                )
        elif sub == "branch":
            deleting = "--delete" in has or "d" in short
            forcing = "--force" in has or "f" in short
            if "D" in short or (deleting and forcing):
                return (
                    "git branch -D",
                    "הפקודה מוחקת ענף גם אם הוא לא מוזג, והקומיטים שבו עלולים ללכת לאיבוד.",
                )
    return None


def check(command, tool=None):
    """Returns (name, why) if the command should be blocked, else None."""
    if recursive_delete(command, tool):
        return NAME_RECURSIVE, WHY_RECURSIVE
    for name, pattern, why in TEXT_RULES:
        if pattern.search(command):
            return name, why
    return git_danger(command)


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        command = data.get("tool_input", {}).get("command", "")
        tool = data.get("tool_name")
    except Exception:
        return
    if not isinstance(command, str):
        return
    try:
        found = check(command, tool)
    except Exception:
        return
    if found:
        name, why = found
        msg = (
            f"נחסם: {name}.\n{why}\n"
            "אם באמת התכוונת לזה, תריצי את הפקודה בעצמך בטרמינל (עם ! לפני הפקודה), "
            "או תבקשי ממני גרסה בטוחה יותר."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": msg,
            },
            "systemMessage": msg,
        }))


if __name__ == "__main__":
    main()
