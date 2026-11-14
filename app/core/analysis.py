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
