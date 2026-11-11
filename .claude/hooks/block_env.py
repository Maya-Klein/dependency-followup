"""PreToolUse hook (project): keeps Claude away from the .env file (it holds the API key).

Blocked:
  - Read / Edit / Write / NotebookEdit / Grep / Glob on a path or glob that names .env or .env.* (not .env.example)
  - Bash / PowerShell commands whose text names .env or .env.* (cat, type, Get-Content, echo >>, python -c "open('.env')", ...)

Reads the hook JSON from stdin. To block, prints a deny decision as JSON and exits 0.
On any parsing problem it allows the call (never breaks the session).

KNOWN LIMITATION: a recursive search in the terminal (for example `grep -r KEY .` over the whole folder) can read
.env without its name appearing in the command, and this hook does not block it. (Claude's own Grep tool is safe
here only because it skips git-ignored files such as .env by default.)

Limits (by design, same as block_dangerous.py): the shell check is on the command text only, so text that merely
mentions .env (a commit message, a grep for "\\.env" in .gitignore) is blocked too, and a determined bypass
(wildcards like ".e*", building the name from pieces) is not caught. The first line of defence is that the key is
never printed anywhere; this hook stops the ordinary ways of reading it by accident.
"""
import json
import re
import sys

ALLOWED_NAMES = {".env.example"}
PATH_KEYS = ("file_path", "notebook_path", "path")  # Read/Edit/Write, NotebookEdit, Grep/Glob
GLOB_KEYS = ("glob",)  # Grep's file filter
# a .env / .env.something token that is not part of a longer word (.venv, os.environ, myfile.env do not match)
ENV_TOKEN = re.compile(r"(?<![\w.])\.env(?:\.[\w-]+)*(?![\w])", re.I)
ENV_BASENAME = re.compile(r"^\.env(\..+)?$", re.I)

WHY = (
    "קובץ ה-.env מכיל את מפתח ה-API וסודות נוספים. קריאה, עריכה או הצגה שלו מכניסות את הסודות לשיחה. "
    "אם צריך לשנות אותו, תעשי את זה בעצמך בעורך, ואם צריך לדעת אילו משתנים הוא מכיל, "
    "השתמשי ב-.env.example."
)


def path_is_env(path: str) -> bool:
    name = path.replace("\\", "/").rstrip("/").split("/")[-1]
    return bool(ENV_BASENAME.match(name)) and name.lower() not in ALLOWED_NAMES


def text_names_env(text: str) -> bool:
    return any(m.group(0).lower() not in ALLOWED_NAMES for m in ENV_TOKEN.finditer(text))


def check(tool, tool_input):
    """Returns True if the call should be blocked."""
    if not isinstance(tool_input, dict):
        return False
    if tool in ("Bash", "PowerShell"):
        command = tool_input.get("command", "")
        return isinstance(command, str) and text_names_env(command)
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and path_is_env(value):
            return True
    for key in GLOB_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and text_names_env(value):
            return True
    if tool == "Glob":
        pattern = tool_input.get("pattern")
        if isinstance(pattern, str) and text_names_env(pattern):
            return True
    return False


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        blocked = check(data.get("tool_name"), data.get("tool_input"))
    except Exception:
        return
    if blocked:
        msg = f"נחסם: גישה לקובץ .env.\n{WHY}"
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
