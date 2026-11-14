import pytest

from app.core.analysis import DIRECTION_CONTROLS, strip_direction_controls

# Invisible characters are always written as visible escapes in this file.
RLO = chr(0x202E)  # U+202E, right-to-left override
LRI = chr(0x2066)  # U+2066, left-to-right isolate
LRM = chr(0x200E)  # U+200E, left-to-right mark
RLM = chr(0x200F)  # U+200F, right-to-left mark

ALL_DANGEROUS = [chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))]


def test_text_without_controls_is_unchanged():
    text = "המשלוח יגיע ביום חמישי"
    assert strip_direction_controls(text) == (text, [])


def test_rlo_in_the_middle_is_removed_and_reported():
    clean, removed = strip_direction_controls("המשלוח" + RLO + "הושלם")
    assert clean == "המשלוחהושלם"
    assert removed == [RLO]


def test_there_are_nine_dangerous_controls():
    assert len(ALL_DANGEROUS) == 9
    assert set(ALL_DANGEROUS) == DIRECTION_CONTROLS


@pytest.mark.parametrize("ch", ALL_DANGEROUS, ids=lambda c: f"U+{ord(c):04X}")
def test_each_dangerous_control_is_removed(ch):
    assert strip_direction_controls("א" + ch + "ב") == ("אב", [ch])


@pytest.mark.parametrize("mark", [LRM, RLM], ids=["LRM", "RLM"])
def test_lrm_and_rlm_stay_and_are_not_reported(mark):
    text = "שלום" + mark + " עולם"
    assert strip_direction_controls(text) == (text, [])


def test_mixed_hebrew_english_emoji_is_unchanged():
    text = "Hi גיל, the crates הגיעו 👍 — thanks!"
    assert strip_direction_controls(text) == (text, [])


def test_empty_string():
    assert strip_direction_controls("") == ("", [])


def test_removed_keeps_order_and_repeats():
    clean, removed = strip_direction_controls(RLO + "א" + LRI + "ב" + RLO)
    assert clean == "אב"
    assert removed == [RLO, LRI, RLO]
