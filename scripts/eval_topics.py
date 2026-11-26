"""Evaluation runs for stage 5 (plan.md, "Decisions for PR C planning", 15.11.2026).

Reads ONLY scripts/<topic>/<topic>_updates.md. The answer-key files are read by
the comparison script and by nothing here.
Does not touch the app, the database or the tests.

Usage:
    python scripts/eval_topics.py --topics 3 --dry-run         # print the request, no API call
    python scripts/eval_topics.py --topics 3,5 --count-tokens  # free: count input tokens
    python scripts/eval_topics.py --count-ceiling              # free: tokens of a maximum-length input
    python scripts/eval_topics.py --topics 3 --runs 1          # real calls (cost money)
    python scripts/eval_topics.py --topics 1-6 --runs 3

Each run is saved to scripts/<topic>/eval/. A refusal, max_tokens, or output that
does not pass the checks is saved as a failure and counted; nothing is retried.
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.analysis import (  # noqa: E402
    EFFORT,
    KIND_THREAD,
    KIND_USER_SUMMARY,
    MAX_CHARS,
    MAX_TOKENS,
    MODEL,
    OUTPUT_CONFIG,
    AnalysisError,
    analyze,
    build_system_prompt,
    build_user_message,
    select_updates,
)
from app.storage.repository import MAX_UPDATE_LENGTHS, THREAD  # noqa: E402

DEFAULT_TODAY = date(2026, 11, 24)  # "today" for the scenario tests (plan.md, decision 8)
# List prices, USD per 1M tokens (Claude Sonnet 5.5; claude-api skill cache, 2026-11-03).
# Thinking is billed as output.
PRICE_IN, PRICE_OUT = 2.00, 10.00
CONTEXT_WINDOW = 1_000_000  # tokens, Claude Sonnet 5.5 (same source)

# Common one-code-point emoji, for the worst case of the ceiling measurement. The app counts code
# points (len), so each of these is one "character" of its limit.
_EMOJI = "".join(map(chr, (0x1F600, 0x1F44D, 0x1F389, 0x1F4E6, 0x1F5BC, 0x2705, 0x1F525,
                           0x1F64F, 0x1F4CE, 0x1F914)))

KIND_BY_LABEL = {
    "התכתבות מודבקת": KIND_THREAD,
    "סיכום שיחה או פגישה": KIND_USER_SUMMARY,
}

Topic = namedtuple("Topic", "name required_outcome deadline our_side updates")
Update = namedtuple("Update", "id entry_date kind content")

_UPDATE_HEADER = re.compile(r"^## עדכון (\d+) · (.+?) · (\d{2}\.\d{2}\.\d{4})[ \t]*$", re.M)


class TopicFormatError(ValueError):
    """The topic file is not in the format this script reads."""


def _parse_date(text, where):
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError as e:
        raise TopicFormatError(f"{where}: not a date: {text!r}") from e


def _field(header, label, name):
    m = re.search(rf"^\*\*{re.escape(label)}:\*\*[ \t]*(.+?)[ \t]*$", header, re.M)
    if not m:
        raise TopicFormatError(f"{name}: missing the line '**{label}:**' above the first '---'")
    return m.group(1)


def parse_topic(text, name):
    """Parse one topic file into a Topic. Raises TopicFormatError with a clear message."""
    header, sep, rest = text.partition("\n---\n")
    if not sep:
        raise TopicFormatError(f"{name}: no '---' line between the header and the updates")
    required_outcome = _field(header, "התוצאה הנדרשת", name)
    deadline = _parse_date(_field(header, "המועד", name), f"{name} deadline")
    our_side = []
    for person in _field(header, "הצד שלנו", name).split(","):
        person = person.strip()
        if person and person not in our_side:
            our_side.append(person)
    if not our_side:
        raise TopicFormatError(f"{name}: '**הצד שלנו:**' has no names")

    updates, seen = [], set()
    matches = list(_UPDATE_HEADER.finditer(rest))
    for i, m in enumerate(matches):
        number = int(m.group(1))
        where = f"{name} update {number}"
        if number in seen:
            raise TopicFormatError(f"{where}: the number appears twice")
        seen.add(number)
        kind = KIND_BY_LABEL.get(m.group(2))
        if kind is None:
            raise TopicFormatError(f"{where}: unknown kind {m.group(2)!r}")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(rest)
        body = re.search(r"```text\n(.*?)\n```", rest[m.end():end], re.S)
        if not body:
            raise TopicFormatError(f"{where}: no ```text block")
        updates.append(Update(number, _parse_date(m.group(3), where), kind, body.group(1)))
    if not updates:
        raise TopicFormatError(f"{name}: no updates found")
    return Topic(name, required_outcome, deadline, our_side, updates)


def load_topic(name):
    path = ROOT / "scripts" / name / f"{name}_updates.md"
    if not path.is_file():
        raise TopicFormatError(f"{name}: {path} does not exist")
    return parse_topic(path.read_text(encoding="utf-8"), name)


def parse_topics_arg(text):
    """"3", "3,5", "1-6", "1-3,5" or a variant such as "7b" -> ["topic3", ...] in order, without repeats."""
    names = []
    for part in text.split(","):
        variant = re.fullmatch(r"\s*(\d+[a-z])\s*", part)
        if variant:
            found = [variant.group(1)]
        else:
            m = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", part)
            if not m:
                raise ValueError(f"cannot read --topics: {text!r}")
            low, high = int(m.group(1)), int(m.group(2) or m.group(1))
            if low > high:
                raise ValueError(f"cannot read --topics: {text!r}")
            found = [str(n) for n in range(low, high + 1)]
        names.extend(f"topic{n}" for n in found if f"topic{n}" not in names)
    return names


def to_jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def cost_usd(meta):
    if not meta:
        return 0.0
    return (meta["input_tokens"] * PRICE_IN + meta["output_tokens"] * PRICE_OUT) / 1_000_000


def build_request(topic, today, max_chars, boundary):
    """The system prompt and user message that analyze would send (no API call)."""
    selected, not_read = select_updates(topic.updates, max_chars)
    system = build_system_prompt(today, topic.our_side, boundary)
    message = build_user_message(topic.required_outcome, topic.deadline, selected, not_read, boundary)
    return system, message, selected, not_read


def count_input(client, topic, today, max_chars):
    """Count the input tokens of one analysis request (free; nothing is analysed). Numbers only."""
    system, message, selected, not_read = build_request(topic, today, max_chars, "count000")
    counted = client.messages.count_tokens(
        model=MODEL, system=system, output_config=OUTPUT_CONFIG,
        messages=[{"role": "user", "content": message}],
    )
    return {
        "updates": len(selected),
        "chars": sum(len(u.content) for u in selected),
        "not_read": len(not_read),
        "input_tokens": counted.input_tokens,
    }


def _filled(source, length):
    """source repeated and cut to exactly this many characters."""
    return (source * (length // len(source) + 1))[:length]


def ceiling_topic(base, filler, max_chars):
    """A made-up topic whose sent updates are exactly max_chars long, shaped like the app would send it.

    The newest update is as long as one thread may be, an older one fills the rest of the ceiling, and an
    even older one does not fit, so the "not read" line is part of the request too.
    """
    newest = min(max_chars, MAX_UPDATE_LENGTHS[THREAD])
    sizes = [1_000, max_chars - newest, newest]
    updates = [
        Update(i, date(2026, 11, i), KIND_THREAD, _filled(filler, size))
        for i, size in enumerate(sizes, start=1) if size
    ]
    return base._replace(name="ceiling", updates=updates)


def measure_ceiling(client, today, max_chars):
    """Token counts for the fixed overhead, a maximum-length Hebrew and emoji input, and topic 1.

    Topic 1 is the control: its count should be close to the input tokens of a real run of it.
    """
    base = load_topic("topic1")
    hebrew = "\n".join(u.content for n in range(1, 7) for u in load_topic(f"topic{n}").updates)
    cases = [
        ("tiny", base._replace(updates=[Update(1, date(2026, 11, 1), KIND_THREAD, "x")])),
        ("hebrew", ceiling_topic(base, hebrew, max_chars)),
        ("emoji", ceiling_topic(base, _EMOJI, max_chars)),
        ("topic1", base),
    ]
    return {name: count_input(client, topic, today, max_chars) for name, topic in cases}


def ceiling_line(name, row):
    tokens = row["input_tokens"]
    fits = "yes" if tokens + MAX_TOKENS <= CONTEXT_WINDOW else "NO"
    return (f"{name}: {row['updates']} updates, {row['chars']} chars, not read: {row['not_read']}, "
            f"{tokens} input tokens, input ${tokens * PRICE_IN / 1_000_000:.4f}, "
            f"with full output ${(tokens * PRICE_IN + MAX_TOKENS * PRICE_OUT) / 1_000_000:.4f}, "
            f"fits the context window: {fits}")


def run_one(client, topic, today, max_chars):
    """One analysis, as a record for the output file. Failures are records too."""
    try:
        result = analyze(
            client, topic.required_outcome, topic.deadline, topic.updates,
            today=today, our_side=topic.our_side, max_chars=max_chars,
        )
    except AnalysisError as e:
        return {
            "ok": False,
            "failure": {"reason": e.reason, "detail": e.detail},
            "result": None,
            "meta": e.meta,
            "cost_usd": round(cost_usd(e.meta), 5),
        }
    return {
        "ok": True,
        "failure": None,
        "result": to_jsonable(result),
        "meta": result["meta"],
        "cost_usd": round(cost_usd(result["meta"]), 5),
    }


def save_record(topic, run_number, stamp, today, record, base=ROOT / "scripts"):
    out_dir = base / topic.name / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{topic.name}_run{run_number}_{stamp}.json"
    full = {"topic": topic.name, "run": run_number, "stamp": stamp, "today": today.isoformat(), **record}
    path.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def require_api_key():
    """Stop with a clear message before any call if the key is not in the environment.

    Only checks that it is set; the value is never read into a variable or printed.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("error: ANTHROPIC_API_KEY is not set. Put it in .env (see .env.example). No call was made.")


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", help='e.g. "3", "3,5", "1-6", "7b" (required except with --count-ceiling)')
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS)
    ap.add_argument("--today", default=DEFAULT_TODAY.strftime("%d.%m.%Y"), help="dd.mm.yyyy")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the request, no API call")
    mode.add_argument("--count-tokens", action="store_true", help="count input tokens (free), no analysis")
    mode.add_argument("--count-ceiling", action="store_true",
                      help="count tokens of a made-up input at the length ceiling (free), no analysis")
    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()
    if not args.topics and not args.count_ceiling:
        ap.error("--topics is required")
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console is cp1255; updates contain emoji

    try:
        today = _parse_date(args.today, "--today")
        names = [] if args.count_ceiling else parse_topics_arg(args.topics)
        topics = [load_topic(name) for name in names]
    except ValueError as e:
        sys.exit(f"error: {e}")

    if args.dry_run:
        for topic in topics:
            try:
                system, message, _, _ = build_request(topic, today, args.max_chars, "dryrun")
            except ValueError as e:
                sys.exit(f"error: {topic.name}: {e}")
            print(f"##### {topic.name}\n=== SYSTEM ===\n{system}\n\n=== USER ===\n{message}\n")
        return

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")  # puts the file's values in the environment; a variable already set wins
    require_api_key()
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment; never printed

    if args.count_ceiling:
        try:
            rows = measure_ceiling(client, today, args.max_chars)
        except anthropic.APIError as e:
            sys.exit(f"error: API error {type(e).__name__}: {e}")
        for name, row in rows.items():
            print(ceiling_line(name, row))
        return

    if args.count_tokens:
        for topic in topics:
            try:
                row = count_input(client, topic, today, args.max_chars)
            except ValueError as e:
                sys.exit(f"error: {topic.name}: {e}")
            print(f"{topic.name}: {row['updates']} updates, {row['chars']} chars of updates, "
                  f"{row['input_tokens']} input tokens (prompt and output schema included), "
                  f"not read: {row['not_read']}")
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    total_cost, seconds, failures, runs_done = 0.0, [], 0, 0
    for topic in topics:
        for n in range(1, args.runs + 1):
            try:
                record = run_one(client, topic, today, args.max_chars)
            except anthropic.APIError as e:
                print(f"{topic.name} run {n}: API error {type(e).__name__}: {e}")
                print(f"stopped. runs done: {runs_done}, cost so far ${total_cost:.4f}")
                sys.exit(1)
            except ValueError as e:
                sys.exit(f"error: {topic.name}: {e}")
            path = save_record(topic, n, stamp, today, record)
            runs_done += 1
            total_cost += record["cost_usd"]
            meta = record["meta"] or {}
            if meta.get("seconds") is not None:
                seconds.append(meta["seconds"])
            if record["ok"]:
                status = f"ok, {len(record['result']['items'])} rows"
            else:
                failures += 1
                status = f"FAILED {record['failure']['reason']}"
            print(f"{topic.name} run {n}: {status}, in={meta.get('input_tokens')} "
                  f"out={meta.get('output_tokens')} ${record['cost_usd']} {meta.get('seconds')}s -> {path}")

    median = statistics.median(seconds) if seconds else 0
    print(f"runs: {runs_done}, failures: {failures}, total cost ${total_cost:.4f}, median {median}s")


if __name__ == "__main__":
    main()
