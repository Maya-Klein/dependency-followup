import unicodedata

EXCERPT_MAX_CHARS = 500
EXCERPT_MAX_LINES = 8


def excerpt(text):
    """First part of a long update, or None when the whole text fits and needs no fold.

    "…" marks the cut, unless the part already ends with punctuation.
    """
    lines = text.split("\n")
    if len(text) <= EXCERPT_MAX_CHARS and len(lines) <= EXCERPT_MAX_LINES:
        return None
    part = "\n".join(lines[:EXCERPT_MAX_LINES])[:EXCERPT_MAX_CHARS].rstrip()
    if unicodedata.category(part[-1]).startswith("P"):
        return part
    return part + "…"
