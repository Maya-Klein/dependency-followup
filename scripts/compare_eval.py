"""Compare saved evaluation runs with the answer key (plan.md, "Decisions for PR C
planning", 15.11.2026, items 3, 4 and 7).

Reads scripts/<topic>/eval/*.json (made by eval_topics.py), scripts/<topic>/<topic>_updates.md
and scripts/<topic>/<topic>_expected.json. Never calls the API.

Per row it compares the STATE and the "what is missing" text, not the tag strings.
Modes:
    improve (default)  metrics and failed rows only; the text of the answer key is not shown
    final              also shows, for each failed row, what the key says (the reported round)

Usage:
    python scripts/compare_eval.py --topics 3
    python scripts/compare_eval.py --topics 1-6 --stamp 20261116-101500 --mode final
    python scripts/compare_eval.py --time-normalization

Answer key, scripts/<topic>/<topic>_expected.json:
    {"rows": [{"name": "...",                          # for the report only
               "match": ["word", "word"],              # a model row belongs here if its name has one of these
               "state": "missing",                     # one of the five states
               "missing_must": [["w1", "w2"], ["w3"]], # each group needs at least one of its words
               "missing_must_not": ["word"],           # none of these may appear
               "missing_empty": false}],               # true: the "missing" text must be empty
     "warnings": {"min": 1, "max": 1, "quote_contains": ["word"]}}   # optional; default: none expected
"""
import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.analysis import (  # noqa: E402
    CONFIRMED,
    KIND_THREAD,
    MISSING,
    NOTE_NO_SUPPORT,
    NOTE_QUOTE_NOT_FOUND,
    STATES,
    normalize_for_match,
)
from scripts.eval_topics import load_topic, parse_topics_arg  # noqa: E402

SCRIPTS = ROOT / "scripts"
NEGATIONS = {"לא", "טרם", "אין", "בלי", "אי"}  # words that flip the meaning of what follows
SHORT_QUOTE_WORDS = 2
_FILE = re.compile(r"(?P<topic>topic\d+)_run(?P<run>\d+)_(?P<stamp>\d{8}-\d{6})\.json")


class AnswerKeyError(ValueError):
    """The answer key file is not in the format this script reads."""


# --- the answer key ---


def parse_answer_key(data, name):
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or not data["rows"]:
        raise AnswerKeyError(f"{name}: needs a non-empty 'rows' list")
    rows = []
    for i, row in enumerate(data["rows"]):
        where = f"{name} row {i + 1}"
        if not isinstance(row, dict):
            raise AnswerKeyError(f"{where}: not an object")
        if not isinstance(row.get("name"), str) or not row["name"].strip():
            raise AnswerKeyError(f"{where}: no name")
        match = row.get("match")
        if not isinstance(match, list) or not match or not all(isinstance(w, str) and w.strip() for w in match):
            raise AnswerKeyError(f"{where}: 'match' must be a non-empty list of words")
        if row.get("state") not in STATES:
            raise AnswerKeyError(f"{where}: unknown state {row.get('state')!r}")
        must = row.get("missing_must", [])
        if not isinstance(must, list) or not all(
            isinstance(g, list) and g and all(isinstance(w, str) and w.strip() for w in g) for g in must
        ):
            raise AnswerKeyError(f"{where}: 'missing_must' must be a list of non-empty word lists")
        must_not = row.get("missing_must_not", [])
        if not isinstance(must_not, list) or not all(isinstance(w, str) and w.strip() for w in must_not):
            raise AnswerKeyError(f"{where}: 'missing_must_not' must be a list of words")
        empty = row.get("missing_empty", False)
        if not isinstance(empty, bool):
            raise AnswerKeyError(f"{where}: 'missing_empty' must be true or false")
        rows.append(
            {"name": row["name"], "match": match, "state": row["state"], "missing_must": must,
             "missing_must_not": must_not, "missing_empty": empty}
        )
    warnings = data.get("warnings", {"min": 0, "max": 0})
    if (
        not isinstance(warnings, dict)
        or not isinstance(warnings.get("min", 0), int)
        or not isinstance(warnings.get("max", 0), int)
        or warnings.get("min", 0) > warnings.get("max", 0)
        or not isinstance(warnings.get("quote_contains", []), list)
    ):
        raise AnswerKeyError(f"{name}: 'warnings' must have whole numbers min <= max and a quote_contains list")
    return {
        "rows": rows,
        "warnings": {
            "min": warnings.get("min", 0),
            "max": warnings.get("max", 0),
            "quote_contains": warnings.get("quote_contains", []),
        },
    }


def load_answer_key(name, base=SCRIPTS):
    path = base / name / f"{name}_expected.json"
    if not path.is_file():
        raise AnswerKeyError(f"{name}: {path} does not exist")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AnswerKeyError(f"{name}: not valid JSON: {e}") from e
    return parse_answer_key(data, name)


# --- matching rows and comparing text ---


def _has(text_norm, word):
    return normalize_for_match(word) in text_norm


def match_rows(key_rows, model_rows):
    """Pair each answer-key row with at most one model row, by the key's words in the model row's name.

    Returns (pairs, extra, ambiguous): pairs maps key index -> model index; extra lists
    model rows that matched nothing, or a key row that already had a pair; ambiguous
    lists model rows whose name matched more than one key row (each goes to the first
    free one).
    """
    pairs, extra, ambiguous = {}, [], []
    for j, row in enumerate(model_rows):
        name = normalize_for_match(row["item"])
        candidates = [i for i, k in enumerate(key_rows) if any(_has(name, w) for w in k["match"])]
        if not candidates:
            extra.append(j)
            continue
        if len(candidates) > 1:
            ambiguous.append(j)
        free = [i for i in candidates if i not in pairs]
        if free:
            pairs[free[0]] = j
        else:
            extra.append(j)
    return pairs, extra, ambiguous


def missing_matches(key_row, missing_text):
    text = normalize_for_match(missing_text)
    if key_row["missing_empty"]:
        return text == ""
    if any(_has(text, w) for w in key_row["missing_must_not"]):
        return False
    return all(any(_has(text, w) for w in group) for group in key_row["missing_must"])


def check_warnings(key, warnings):
    """Count and content of the injection warnings against the key."""
    want = key["warnings"]
    quotes = normalize_for_match(" ".join(w["quote"] for w in warnings))
    return {
        "count": len(warnings),
        "count_ok": want["min"] <= len(warnings) <= want["max"],
        "false_alarms": max(0, len(warnings) - want["max"]),
        "content_ok": all(_has(quotes, w) for w in want["quote_contains"]),
        "unverified": sum(1 for w in warnings if not w.get("verified")),
    }


# --- measurements from "what to check in PR C" ---


def _loose(text):
    return re.sub(r"[\W_]+", "", text).lower()


def quote_stats(topic, items):
    """Short verified quotes, verified quotes right after a negation word, and
    unverified quotes that a looser comparison would have found (a normalization problem)."""
    normalized = {u.id: normalize_for_match(u.content) for u in topic.updates}
    loose = {u.id: _loose(u.content) for u in topic.updates}
    short, negated, normalization = [], [], []
    for item in items:
        for f in item["findings"]:
            quote = normalize_for_match(f["quote"])
            if not quote:
                continue
            example = {"quote": f["quote"], "state": item["state"], "tag": f["tag"]}
            if f["verified"]:
                if len(quote.split()) <= SHORT_QUOTE_WORDS:
                    short.append(example)
                record = normalized.get(f["update_id"], "")
                at = record.find(quote)
                if at > 0 and any(w in NEGATIONS for w in record[:at].split()[-2:]):
                    negated.append(example)
            elif _loose(f["quote"]) and _loose(f["quote"]) in loose.get(f["update_id"], ""):
                normalization.append(example)
    return {"short": short, "negated": negated, "normalization": normalization}


def downgrade_stats(topic, items):
    """How many rows the code lowered, and why (only reasons the code records)."""
    kinds = {u.id: u.kind for u in topic.updates}
    lowered = quote_not_found = unclear_writer = 0
    for item in items:
        before = item.get("model_state", item["state"])
        if before == item["state"]:
            continue
        lowered += 1
        if item["note"] == NOTE_QUOTE_NOT_FOUND:
            quote_not_found += 1
        if (
            before == CONFIRMED
            and item["note"] == NOTE_NO_SUPPORT
            and any(
                f["verified"] and f["tag"] == "written" and f["who"] == "unclear"
                and kinds.get(f["update_id"]) == KIND_THREAD
                for f in item["findings"]
            )
        ):
            unclear_writer += 1
    return {"lowered": lowered, "quote_not_found": quote_not_found, "unclear_writer": unclear_writer}


# --- one run, one topic ---


def score_run(key, topic, record):
    if not record["ok"]:
        return {"ok": False, "reason": record["failure"]["reason"], "cost": record.get("cost_usd", 0.0),
                "seconds": (record.get("meta") or {}).get("seconds")}
    result = record["result"]
    items = result["items"]
    pairs, extra, ambiguous = match_rows(key["rows"], items)
    rows = []
    for i, krow in enumerate(key["rows"]):
        j = pairs.get(i)
        if j is None:
            rows.append({"matched": False, "model_name": None, "state": None, "missing_text": None,
                         "state_ok": False, "missing_ok": False})
            continue
        model = items[j]
        rows.append({
            "matched": True,
            "model_name": model["item"],
            "state": model["state"],
            "missing_text": model["missing"],
            "state_ok": model["state"] == krow["state"],
            "missing_ok": missing_matches(krow, model["missing"]),
        })
    return {
        "ok": True,
        "rows": rows,
        "extra_rows": len(extra),
        "ambiguous": len(ambiguous),
        "warnings": check_warnings(key, result["injection_warnings"]),
        "quotes": quote_stats(topic, items),
        "downgrades": downgrade_stats(topic, items),
        "cost": record.get("cost_usd", 0.0),
        "seconds": (record.get("meta") or {}).get("seconds"),
    }


def inconsistent_rows(key, scored_runs):
    """Key rows whose model state is not the same in every successful run.
    An unmatched row counts as its own value."""
    good = [r for r in scored_runs if r["ok"]]
    result = []
    for i in range(len(key["rows"])):
        values = {r["rows"][i]["state"] or "unmatched" for r in good}
        if len(values) > 1:
            result.append(i)
    return result


# --- reading saved runs ---


def find_runs(name, stamps, base=SCRIPTS):
    """Saved runs of a topic as (label, record). Without stamps: the latest stamp only."""
    found = []
    folder = base / name / "eval"
    for path in sorted(folder.glob(f"{name}_run*_*.json")) if folder.is_dir() else []:
        m = _FILE.fullmatch(path.name)
        if m and m["topic"] == name:
            found.append((m["stamp"], int(m["run"]), path))
    if stamps:
        found = [f for f in found if f[0] in stamps]
    elif found:
        latest = max(f[0] for f in found)
        found = [f for f in found if f[0] == latest]
    found.sort()
    return [(f"{stamp}#{run}", json.loads(path.read_text(encoding="utf-8"))) for stamp, run, path in found]


# --- the report ---


def _pct(part, whole):
    return f"{part}/{whole}" + (f" ({round(100 * part / whole)}%)" if whole else "")


def render_topic(name, key, topic, labelled_scores, mode):
    scored = [s for _, s in labelled_scores]
    good = [s for s in scored if s["ok"]]
    rows_total = len(good) * len(key["rows"])
    lines = [f"== {name}: {len(scored)} runs, {len(scored) - len(good)} failed"]
    for label, s in labelled_scores:
        if not s["ok"]:
            lines.append(f"   FAILED {label}: {s['reason']}")
    if not good:
        return lines
    lines.append(f"   state correct: {_pct(sum(r['state_ok'] for s in good for r in s['rows']), rows_total)}")
    lines.append(f"   'what is missing' correct: {_pct(sum(r['missing_ok'] for s in good for r in s['rows']), rows_total)}")
    lines.append(f"   key rows with no model row: {sum(not r['matched'] for s in good for r in s['rows'])}, "
                 f"extra model rows per run: {[s['extra_rows'] for s in good]}, "
                 f"ambiguous names: {sum(s['ambiguous'] for s in good)}")
    bad = inconsistent_rows(key, scored)
    lines.append("   consistency: " + ("consistent" if not bad else
                                     f"INCONSISTENT in {len(bad)} row(s) - run 2 more times"))
    w = [s["warnings"] for s in good]
    lines.append(f"   injection warnings: count ok {_pct(sum(x['count_ok'] for x in w), len(w))}, "
                 f"content ok {_pct(sum(x['content_ok'] for x in w), len(w))}, "
                 f"false alarms {sum(x['false_alarms'] for x in w)}, unverified {sum(x['unverified'] for x in w)}")
    q = [s["quotes"] for s in good]
    lines.append(f"   short verified quotes (<= {SHORT_QUOTE_WORDS} words): {sum(len(x['short']) for x in q)}, "
                 f"after a negation word: {sum(len(x['negated']) for x in q)}, "
                 f"looser match would have verified: {sum(len(x['normalization']) for x in q)}")
    d = [s["downgrades"] for s in good]
    lines.append(f"   rows lowered by the code: {sum(x['lowered'] for x in d)} "
                 f"(quote not found {sum(x['quote_not_found'] for x in d)}, "
                 f"writer 'unclear' kept 'confirmed in writing' from the other side {sum(x['unclear_writer'] for x in d)})")
    for label, s in labelled_scores:
        if not s["ok"]:
            continue
        for i, r in enumerate(s["rows"]):
            if r["state_ok"] and r["missing_ok"]:
                continue
            if not r["matched"]:
                text = f"   failed row, {label}: a key row has no model row"
                if mode == "final":
                    text += f" ({key['rows'][i]['name']})"
                lines.append(text)
                continue
            kinds = ", ".join(k for k, ok in (("state", r["state_ok"]), ("missing text", r["missing_ok"])) if not ok)
            text = f"   failed row, {label}: model row {r['model_name']!r} state={r['state']} ({kinds} differs)"
            if mode == "final":
                k = key["rows"][i]
                text += f"\n      key: {k['name']!r} state={k['state']} must={k['missing_must']} " \
                        f"must_not={k['missing_must_not']} empty={k['missing_empty']}; model said: {r['missing_text']!r}"
            lines.append(text)
    if mode == "final":
        for label, s in labelled_scores:
            if s["ok"]:
                for kind in ("short", "negated", "normalization"):
                    for ex in s["quotes"][kind]:
                        lines.append(f"   {kind} quote, {label}: {ex['quote']!r} state={ex['state']} tag={ex['tag']}")
    return lines


def time_normalization(chars=250_000):
    """Seconds to normalize a text of this length once (plan.md: check if it gets in the way)."""
    sample = ("הארגזים הגיעו למחסן, לא אושר > עדיין. " * (chars // 30 + 1))[:chars]
    started = time.monotonic()
    normalize_for_match(sample)
    return time.monotonic() - started


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", help='e.g. "3", "3,5", "1-6"')
    ap.add_argument("--stamp", action="append", default=[], help="a run stamp; repeat to add runs. Default: the latest")
    ap.add_argument("--mode", choices=("improve", "final"), default="improve")
    ap.add_argument("--time-normalization", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.time_normalization:
        print(f"normalize_for_match on 250,000 characters: {time_normalization():.3f}s")
        if not args.topics:
            return
    if not args.topics:
        sys.exit("error: --topics is required")

    all_scores, total_cost, seconds = [], 0.0, []
    for name in parse_topics_arg(args.topics):
        try:
            topic, key = load_topic(name), load_answer_key(name)
        except ValueError as e:
            sys.exit(f"error: {e}")
        runs = find_runs(name, set(args.stamp))
        if not runs:
            print(f"== {name}: no saved runs")
            continue
        labelled = [(label, score_run(key, topic, rec)) for label, rec in runs]
        for line in render_topic(name, key, topic, labelled, args.mode):
            print(line)
        for _, s in labelled:
            total_cost += s["cost"]
            if s["seconds"] is not None:
                seconds.append(s["seconds"])
        all_scores.extend(s for _, s in labelled)
    print(f"-- runs: {len(all_scores)}, failed: {sum(not s['ok'] for s in all_scores)}, "
          f"cost ${total_cost:.4f}, median {statistics.median(seconds) if seconds else 0}s")


if __name__ == "__main__":
    main()
