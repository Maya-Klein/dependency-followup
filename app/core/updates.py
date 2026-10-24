EXCERPT_MAX_CHARS = 500
EXCERPT_MAX_LINES = 8


def excerpt(text):
    """First part of a long update, or None when the whole text fits and needs no fold."""
    lines = text.split("\n")
    if len(text) <= EXCERPT_MAX_CHARS and len(lines) <= EXCERPT_MAX_LINES:
        return None
    return "\n".join(lines[:EXCERPT_MAX_LINES])[:EXCERPT_MAX_CHARS].rstrip() + "…"
