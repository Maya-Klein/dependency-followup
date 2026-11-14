# Characters that reorder how text is displayed (embeddings, overrides, isolates).
# LRM/RLM (U+200E/U+200F) are harmless marks common in Hebrew text, so they stay.
DIRECTION_CONTROLS = frozenset(
    chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
)


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
