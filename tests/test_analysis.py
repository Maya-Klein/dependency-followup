import copy
import unicodedata
from collections import namedtuple
from datetime import date

import pytest

from app.core.analysis import (
    COMMITMENT,
    CONFIRMED,
    DECISION,
    DIRECTION_CONTROLS,
    KIND_THREAD,
    KIND_USER_SUMMARY,
    MISSING,
    NO_LONGER_REQUIRED,
    NOTE_NO_SUPPORT,
    NOTE_QUOTE_NOT_FOUND,
    OPINION,
    OTHER,
    OURS,
    PROCEEDING,
    REPORTED,
    REPORTED_DONE,
    UNCLEAR,
    WRITTEN,
    enforce_states,
    normalize_for_match,
    quote_in_record,
    select_updates,
    strip_direction_controls,
)
from app.storage.repository import THREAD, USER_SUMMARY

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


# --- quote_in_record and normalize_for_match ---

GERSHAYIM = chr(0x05F4)  # U+05F4, Hebrew double quote
GERESH = chr(0x05F3)  # U+05F3, Hebrew single quote
CURLY = chr(0x2019)  # U+2019, right single quotation mark

RECORD = "גיל כתב:\nהארגזים יגיעו ביום חמישי, ואז נארוז."


def test_quote_found_word_for_word():
    assert quote_in_record("הארגזים יגיעו ביום חמישי", RECORD)


def test_quote_not_in_record():
    assert not quote_in_record("המשלוח הושלם", RECORD)


def test_quote_from_another_record_is_not_found_here():
    other = "עמית דיווח בטלפון שהפסל נארז."
    assert quote_in_record("הפסל נארז", other)
    assert not quote_in_record("הפסל נארז", RECORD)


def test_partial_quote_counts():
    assert quote_in_record("יגיעו ביום", RECORD)


def test_reply_markers_in_record_are_ignored():
    record = "> > הארגזים יגיעו\n> ביום חמישי\nתודה"
    assert quote_in_record("הארגזים יגיעו ביום חמישי", record)
    assert quote_in_record("> הארגזים יגיעו", record)


def test_line_breaks_and_extra_spaces_are_unified():
    record = "הארגזים   יגיעו\r\nביום\n\n חמישי"
    assert quote_in_record("הארגזים יגיעו ביום חמישי", record)


@pytest.mark.parametrize("mark", [RLO, LRM, RLM], ids=["RLO", "LRM", "RLM"])
def test_direction_characters_do_not_matter(mark):
    assert quote_in_record("ביום" + mark + " חמישי", RECORD)
    assert quote_in_record("ביום חמישי", "ביום" + mark + " חמישי")


@pytest.mark.parametrize(
    "ch",
    [chr(0x200B), chr(0xFEFF), chr(0x2060), chr(0x061C)],
    ids=["ZWSP", "BOM", "word-joiner", "ALM"],
)
def test_every_invisible_format_character_is_ignored(ch):
    assert unicodedata.category(ch) == "Cf"
    assert quote_in_record("ביום חמישי", "ביום" + ch + " חמישי")
    assert quote_in_record("ביום" + ch + " חמישי", "ביום חמישי")
    assert quote_in_record(ch + "הארגזים יגיעו", RECORD)


def test_gershayim_equals_plain_double_quote():
    with_gershayim = "הוא אמר " + GERSHAYIM + "בסדר" + GERSHAYIM
    assert quote_in_record('הוא אמר "בסדר"', with_gershayim)
    assert quote_in_record(with_gershayim, 'הוא אמר "בסדר"')


def test_geresh_equals_plain_single_quote():
    assert quote_in_record("צ" + GERESH + "ק", "הגיע צ'ק")
    assert quote_in_record("צ'ק", "הגיע צ" + GERESH + "ק")


def test_curly_apostrophe_equals_plain_single_quote():
    assert quote_in_record("it" + CURLY + "s done", "Gil: it's done")
    assert quote_in_record("it's done", "Gil: it" + CURLY + "s done")


def test_left_curly_double_quote_equals_plain_double_quote():
    record = "הוא אמר " + chr(0x201C) + "בסדר" + chr(0x201D)
    assert quote_in_record('הוא אמר "בסדר"', record)
    assert quote_in_record(record, 'הוא אמר "בסדר"')


def test_right_curly_double_quote_equals_plain_double_quote():
    assert quote_in_record('בסדר"', "הוא אמר בסדר" + chr(0x201D))
    assert quote_in_record("בסדר" + chr(0x201D), 'הוא אמר בסדר"')


def test_left_curly_single_quote_equals_plain_single_quote():
    assert quote_in_record("say 'ok", "Gil: say " + chr(0x2018) + "ok")
    assert quote_in_record("say " + chr(0x2018) + "ok", "Gil: say 'ok")


def test_empty_or_blank_quote_never_passes():
    assert not quote_in_record("", RECORD)
    assert not quote_in_record("  \n ", RECORD)
    assert not quote_in_record("", "")


def test_case_matters_in_english():
    assert quote_in_record("Crates arrived", "Gil: Crates arrived today")
    assert not quote_in_record("crates arrived", "Gil: Crates arrived today")


def test_hebrew_english_emoji_mix():
    record = "Gil: ציוד האריזה הגיע 👍 thanks!"
    assert quote_in_record("הגיע 👍 thanks", record)


def test_normalize_is_idempotent():
    messy = "> > א" + RLO + "  ב\r\n" + LRM + "> ג" + GERSHAYIM
    once = normalize_for_match(messy)
    assert normalize_for_match(once) == once
    assert once == 'א ב ג"'


# --- select_updates ---

Update = namedtuple("Update", "id entry_date content created_at")


def upd(id, day, size, created_at=0):
    return Update(id, date(2026, 11, day), "x" * size, created_at)


def ids(updates):
    return [u.id for u in updates]


def test_everything_fits():
    updates = [upd(1, 1, 10), upd(2, 2, 10)]
    selected, not_read = select_updates(updates, 100)
    assert ids(selected) == [1, 2]
    assert not_read == []


def test_sorted_by_entry_date_even_if_given_unsorted():
    updates = [upd(3, 9, 5), upd(1, 2, 5), upd(2, 5, 5)]
    selected, _ = select_updates(updates, 100)
    assert ids(selected) == [1, 2, 3]


def test_same_date_is_ordered_by_id():
    updates = [upd(7, 4, 5), upd(5, 4, 5), upd(6, 4, 5)]
    selected, _ = select_updates(updates, 100)
    assert ids(selected) == [5, 6, 7]


def test_created_at_does_not_affect_order():
    updates = [upd(1, 1, 5, created_at=99), upd(2, 2, 5, created_at=1)]
    selected, _ = select_updates(updates, 100)
    assert ids(selected) == [1, 2]


def test_over_the_ceiling_drops_the_oldest():
    updates = [upd(1, 1, 40), upd(2, 2, 40), upd(3, 3, 40)]
    selected, not_read = select_updates(updates, 100)
    assert ids(selected) == [2, 3]
    assert not_read == [(1, date(2026, 11, 1))]


def test_update_that_does_not_fit_is_dropped_whole_and_older_ones_do_not_skip_past_it():
    updates = [upd(1, 1, 10), upd(2, 2, 90), upd(3, 3, 20)]
    selected, not_read = select_updates(updates, 100)
    assert ids(selected) == [3]
    assert [i for i, _ in not_read] == [1, 2]


def test_newest_update_always_goes_in_whole():
    updates = [upd(1, 1, 10), upd(2, 2, 100)]
    selected, not_read = select_updates(updates, 100)
    assert ids(selected) == [2]
    assert len(selected[0].content) == 100
    assert not_read == [(1, date(2026, 11, 1))]


def test_not_read_has_id_and_date_oldest_first():
    updates = [upd(1, 1, 30), upd(2, 2, 30), upd(3, 3, 30), upd(4, 4, 30)]
    _, not_read = select_updates(updates, 60)
    assert not_read == [(1, date(2026, 11, 1)), (2, date(2026, 11, 2))]


def test_no_updates():
    assert select_updates([], 100) == ([], [])


def test_ceiling_smaller_than_the_newest_update_raises():
    with pytest.raises(ValueError):
        select_updates([upd(1, 1, 10), upd(2, 2, 101)], 100)


# --- enforce_states ---

Record = namedtuple("Record", "id kind content")

RECORDS = [
    Record(1, KIND_THREAD, "גיל כתב: הארגזים הגיעו ואנחנו מאשרים את המשלוח"),
    Record(2, KIND_USER_SUMMARY, "עמית אמר בטלפון שהפסל נארז"),
    Record(3, KIND_THREAD, "החלטנו להתקדם גם בלי תעודת הביטוח"),
]

Q1 = "אנחנו מאשרים את המשלוח"  # in record 1
Q2 = "הפסל נארז"  # in record 2
Q3 = "החלטנו להתקדם"  # in record 3


def finding(tag, who, update_id, quote):
    return {"tag": tag, "who": who, "update_id": update_id, "quote": quote}


def item(state, *findings):
    return {"name": "פריט", "state": state, "findings": list(findings)}


def run_one(state, *findings):
    return enforce_states([item(state, *findings)], RECORDS)[0]


def test_kind_constants_match_storage():
    assert KIND_THREAD == THREAD
    assert KIND_USER_SUMMARY == USER_SUMMARY


@pytest.mark.parametrize(
    "state, f",
    [
        (CONFIRMED, finding(WRITTEN, OTHER, 1, Q1)),
        (REPORTED_DONE, finding(REPORTED, OTHER, 2, Q2)),
        (REPORTED_DONE, finding(WRITTEN, OTHER, 1, Q1)),
        (NO_LONGER_REQUIRED, finding(DECISION, OURS, 3, Q3)),
        (PROCEEDING, finding(DECISION, OURS, 2, Q2)),
    ],
    ids=["confirmed", "reported-by-reported", "reported-by-written", "no-longer", "proceeding-from-summary"],
)
def test_state_with_a_verified_supporting_finding_stays(state, f):
    row = run_one(state, f)
    assert row["state"] == state
    assert row["note"] is None
    assert row["findings"][0]["verified"] is True


@pytest.mark.parametrize("who", [OURS, UNCLEAR])
def test_confirmed_needs_the_other_side_as_writer(who):
    row = run_one(CONFIRMED, finding(WRITTEN, who, 1, Q1))
    assert row["state"] == MISSING
    assert row["note"] == NOTE_NO_SUPPORT


def test_written_from_a_user_summary_counts_as_reported():
    f = finding(WRITTEN, OTHER, 2, Q2)
    row = run_one(REPORTED_DONE, f)
    assert row["state"] == REPORTED_DONE
    assert row["findings"][0]["effective_tag"] == REPORTED
    row = run_one(CONFIRMED, f)
    assert row["state"] == MISSING
    assert row["note"] == NOTE_NO_SUPPORT


@pytest.mark.parametrize("tag", [OPINION, COMMITMENT])
@pytest.mark.parametrize("state", [CONFIRMED, REPORTED_DONE, NO_LONGER_REQUIRED, PROCEEDING])
def test_opinion_and_commitment_support_no_state(state, tag):
    row = run_one(state, finding(tag, OTHER, 1, Q1))
    assert row["state"] == MISSING
    assert row["note"] == NOTE_NO_SUPPORT


def test_quote_not_found_marks_unverified_and_drops():
    row = run_one(CONFIRMED, finding(WRITTEN, OTHER, 1, "המשלוח הושלם"))
    assert row["state"] == MISSING
    assert row["note"] == NOTE_QUOTE_NOT_FOUND
    assert row["findings"][0]["verified"] is False


def test_quote_from_another_record_is_not_verified():
    row = run_one(REPORTED_DONE, finding(REPORTED, OTHER, 2, Q1))
    assert row["findings"][0]["verified"] is False
    assert row["state"] == MISSING
    assert row["note"] == NOTE_QUOTE_NOT_FOUND


def test_one_verified_finding_is_enough():
    row = run_one(
        REPORTED_DONE,
        finding(REPORTED, OTHER, 2, "משהו שלא נאמר"),
        finding(REPORTED, OTHER, 2, Q2),
    )
    assert row["state"] == REPORTED_DONE
    assert [f["verified"] for f in row["findings"]] == [False, True]


def test_unknown_update_id_is_unverified():
    row = run_one(REPORTED_DONE, finding(REPORTED, OTHER, 99, Q2))
    assert row["findings"][0]["verified"] is False
    assert row["state"] == MISSING
    assert row["note"] == NOTE_QUOTE_NOT_FOUND


def test_missing_is_never_raised():
    row = run_one(MISSING, finding(WRITTEN, OTHER, 1, Q1), finding(DECISION, OURS, 3, Q3))
    assert row["state"] == MISSING
    assert row["note"] is None


@pytest.mark.parametrize(
    "row",
    [
        item("done", finding(WRITTEN, OTHER, 1, Q1)),
        item(CONFIRMED, finding("rumour", OTHER, 1, Q1)),
        item(CONFIRMED, finding(WRITTEN, "someone", 1, Q1)),
    ],
    ids=["state", "tag", "writer"],
)
def test_unknown_values_are_rejected(row):
    with pytest.raises(ValueError):
        enforce_states([row], RECORDS)


def good_finding(**changes):
    return {**finding(WRITTEN, OTHER, 1, Q1), **changes}


@pytest.mark.parametrize(
    "row",
    [
        "not a dict",
        {"findings": []},
        {"state": CONFIRMED},
        {"state": CONFIRMED, "findings": None},
        {"state": CONFIRMED, "findings": "text"},
        {"state": ["x"], "findings": []},
        {"state": CONFIRMED, "findings": ["not a dict"]},
        {"state": CONFIRMED, "findings": [{"tag": WRITTEN, "who": OTHER, "update_id": 1}]},
        {"state": CONFIRMED, "findings": [good_finding(quote=None)]},
        {"state": CONFIRMED, "findings": [good_finding(quote=5)]},
        {"state": CONFIRMED, "findings": [good_finding(update_id=[1])]},
        {"state": CONFIRMED, "findings": [good_finding(update_id="1")]},
        {"state": CONFIRMED, "findings": [good_finding(update_id=True)]},
        {"state": CONFIRMED, "findings": [good_finding(tag=None)]},
        {"state": CONFIRMED, "findings": [good_finding(who=["ours"])]},
    ],
)
def test_malformed_rows_are_rejected_with_value_error(row):
    with pytest.raises(ValueError):
        enforce_states([row], RECORDS)


def test_input_is_not_changed():
    rows = [item(CONFIRMED, finding(WRITTEN, OURS, 1, Q1))]
    before = copy.deepcopy(rows)
    enforce_states(rows, RECORDS)
    assert rows == before
