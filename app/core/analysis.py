import re

# Characters that reorder how text is displayed (embeddings, overrides, isolates).
# LRM/RLM (U+200E/U+200F) are harmless marks common in Hebrew text, so they stay
# in stored and displayed text, and are dropped only when comparing quotes.
DIRECTION_CONTROLS = frozenset(
    chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
)
DIRECTION_MARKS = (chr(0x200E), chr(0x200F))  # LRM, RLM

# Hebrew gershayim and geresh, and the curly quotes and apostrophes, count as
# the plain marks.
_QUOTE_MARKS = str.maketrans(
    {
        chr(0x05F4): '"',  # Hebrew gershayim
        chr(0x201C): '"',  # left double quotation mark
        chr(0x201D): '"',  # right double quotation mark
        chr(0x05F3): "'",  # Hebrew geresh
        chr(0x2018): "'",  # left single quotation mark
        chr(0x2019): "'",  # right single quotation mark
    }
)
# Reply markers at the start of a line: "> ", "> > ", ">>".
_REPLY_MARKERS = re.compile(r"^[ \t]*(?:>[ \t]*)+", re.MULTILINE)


def strip_direction_controls(text):
    """Return (clean_text, removed): the text without display-reversing characters,
    and the list of characters that were removed, in order of appearance.

    The stored text is never changed; this cleans a copy before display,
    analysis and quote checking.
    """
    removed = [ch for ch in text if ch in DIRECTION_CONTROLS]
    if not removed:
        return text, []
    clean = "".join(ch for ch in text if ch not in DIRECTION_CONTROLS)
    return clean, removed


def normalize_for_match(text):
    """Prepare text for quote comparison; used on the quote and on the record alike.

    Drops direction controls (including LRM and RLM) and reply markers at line
    starts, treats the Hebrew and plain quote marks as equal, and collapses all
    whitespace to single spaces.
    """
    text, _ = strip_direction_controls(text)
    for mark in DIRECTION_MARKS:
        text = text.replace(mark, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _REPLY_MARKERS.sub("", text)
    text = text.translate(_QUOTE_MARKS)
    return " ".join(text.split())


def quote_in_record(quote, record_text):
    """True if the quote appears word for word inside this one record.

    Any continuous part of the record counts, so a very short quote can pass
    without proving much (a risk to measure in PR C). An empty quote never passes.
    """
    wanted = normalize_for_match(quote)
    if not wanted:
        return False
    return wanted in normalize_for_match(record_text)


def select_updates(updates, max_chars):
    """Choose which updates go to the analysis, within a total length ceiling.

    Each update needs .id, .entry_date and .content. Returns (selected, not_read):
    selected is oldest to newest, ordered by entry_date and then id (created_at is
    not used). When the total is too long the oldest updates are dropped whole,
    never cut in the middle, and not_read lists them as (id, entry_date) pairs.
    The newest update always goes in whole; if it alone exceeds max_chars the
    ceiling is wrong, so this raises instead of cutting silently.
    """
    ordered = sorted(updates, key=lambda u: (u.entry_date, u.id))
    if not ordered:
        return [], []
    if len(ordered[-1].content) > max_chars:
        raise ValueError("max_chars is smaller than the newest update")
    total = 0
    start = len(ordered)
    for i in range(len(ordered) - 1, -1, -1):
        size = len(ordered[i].content)
        if total + size > max_chars:
            break
        total += size
        start = i
    not_read = [(u.id, u.entry_date) for u in ordered[:start]]
    return ordered[start:], not_read


# --- states, tags and the mapping between them (one place, decision 6) ---

CONFIRMED = "confirmed_in_writing"
REPORTED_DONE = "reported_done"
MISSING = "missing"
NO_LONGER_REQUIRED = "no_longer_required"
PROCEEDING = "proceeding_without_full_confirmation"
STATES = (CONFIRMED, REPORTED_DONE, MISSING, NO_LONGER_REQUIRED, PROCEEDING)

STATE_LABELS = {
    CONFIRMED: "מאושר בכתב",
    REPORTED_DONE: "בוצע לפי דיווח",
    MISSING: "חסר",
    NO_LONGER_REQUIRED: "לא נדרש עוד",
    PROCEEDING: "הוחלט להתקדם בלי אישור מלא",
}

WRITTEN = "written"
REPORTED = "reported"
OPINION = "opinion"
COMMITMENT = "commitment"
DECISION = "decision"
TAGS = (WRITTEN, REPORTED, OPINION, COMMITMENT, DECISION)

OURS = "ours"
OTHER = "other"
UNCLEAR = "unclear"
WHO_WROTE = (OURS, OTHER, UNCLEAR)

# Same values as THREAD and USER_SUMMARY in storage/repository.py (core must not
# import storage; a test checks they match).
KIND_THREAD = "thread"
KIND_USER_SUMMARY = "user_summary"

# Which (effective) tags can support a state. Opinion and commitment support no
# state other than "missing". "Confirmed in writing" also needs the other side as
# the writer (checked in _fits). A user summary never reaches "written": see
# effective_tag.
SUPPORTING_TAGS = {
    CONFIRMED: {WRITTEN},
    REPORTED_DONE: {REPORTED, WRITTEN},
    NO_LONGER_REQUIRED: {DECISION},
    PROCEEDING: {DECISION},
}

NOTE_QUOTE_NOT_FOUND = "הציטוט לא נמצא בעדכון"
NOTE_NO_SUPPORT = "אין ממצא תומך במצב"


def effective_tag(tag, kind):
    """A "written" finding that comes from the user's own summary counts as "reported"."""
    if tag == WRITTEN and kind == KIND_USER_SUMMARY:
        return REPORTED
    return tag


def _fits(state, finding, kind):
    """Would this finding support the state, if its quote were verified?"""
    tag = effective_tag(finding["tag"], kind)
    if tag not in SUPPORTING_TAGS[state]:
        return False
    if state == CONFIRMED:
        return finding["who"] == OTHER
    return True


def _check_values(item):
    if item["state"] not in STATES:
        raise ValueError(f"unknown state: {item['state']!r}")
    for finding in item["findings"]:
        if finding["tag"] not in TAGS:
            raise ValueError(f"unknown tag: {finding['tag']!r}")
        if finding["who"] not in WHO_WROTE:
            raise ValueError(f"unknown writer: {finding['who']!r}")


def enforce_states(items, updates):
    """Check the model's rows in code. Returns new rows; the input is not changed.

    items: dicts with "state" and "findings"; each finding has "tag", "who",
    "update_id" and "quote". updates: objects with .id, .kind and .content, the
    records the findings come from.

    Every finding gets "verified" (its quote is found in the record it names) and
    "effective_tag". A row whose state has no verified supporting finding drops to
    "missing" with a "note"; a row is never raised, and "missing" is left alone.
    Unknown states, tags or writers raise ValueError (the output is rejected).
    """
    records = {u.id: u for u in updates}
    result = []
    for item in items:
        _check_values(item)
        findings = []
        for finding in item["findings"]:
            record = records.get(finding["update_id"])
            kind = record.kind if record else None
            verified = bool(record) and quote_in_record(finding["quote"], record.content)
            findings.append(
                {
                    **finding,
                    "verified": verified,
                    "effective_tag": effective_tag(finding["tag"], kind),
                    "_fits": item["state"] != MISSING and _fits(item["state"], finding, kind),
                }
            )
        state, note = item["state"], None
        if state != MISSING and not any(f["_fits"] and f["verified"] for f in findings):
            state = MISSING
            note = (
                NOTE_QUOTE_NOT_FOUND
                if any(f["_fits"] for f in findings)
                else NOTE_NO_SUPPORT
            )
        for f in findings:
            del f["_fits"]
        result.append({**item, "state": state, "note": note, "findings": findings})
    return result
