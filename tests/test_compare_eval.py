import json
from pathlib import Path

import pytest

from scripts import compare_eval as ce
from scripts import eval_topics as ev

TOPIC_TEXT = """# נושא 9

**התוצאה הנדרשת:** הכל מוכן

**המועד:** 30.11.2026

**הצד שלנו:** תמר

---

## עדכון 1 · התכתבות מודבקת · 16.11.2026

```text
המסמך לא אושר עדיין. הכל הושלם והתשלום בוצע
```

## עדכון 2 · סיכום שיחה או פגישה · 17.11.2026

```text
דיברתי עם גיל
```
"""
TOPIC = ev.parse_topic(TOPIC_TEXT, "topic9")

KEY = ce.parse_answer_key(
    {
        "rows": [
            {"name": "שם-סודי-א", "match": ["מסמך"], "state": "missing",
             "missing_must": [["חתום", "חתימה"], ["אישור"]], "missing_must_not": ["הכל מוכן"]},
            {"name": "שם-סודי-ב", "match": ["תשלום"], "state": "reported_done", "missing_empty": True},
        ]
    },
    "topic9",
)


def finding(update_id, quote, verified=True, tag="written", who="other"):
    return {"update_id": update_id, "quote": quote, "verified": verified, "tag": tag, "who": who,
            "note": "", "effective_tag": tag, "also_in_earlier": []}


def item(name, state, missing="", findings=(), model_state=None, note=None):
    return {"item": name, "state": state, "missing": missing, "findings": list(findings),
            "model_state": model_state or state, "note": note}


def record(items, warnings=(), direction=(), not_assessable=()):
    return {
        "ok": True, "failure": None, "cost_usd": 0.02, "meta": {"seconds": 12.5},
        "result": {"items": items, "injection_warnings": list(warnings),
                   "not_assessable": list(not_assessable),
                   "not_read": [], "direction_warnings": list(direction), "meta": {}},
    }


GOOD_ITEMS = [
    item("המסמך החתום", "missing", "חסרה חתימה ואישור"),
    item("התשלום", "reported_done", ""),
]


# --- the answer key ---


def test_a_good_answer_key_is_read_with_defaults():
    assert KEY["rows"][1]["missing_empty"] is True
    assert KEY["rows"][0]["missing_must_not"] == ["הכל מוכן"]
    assert KEY["warnings"] == {"min": 0, "max": 0, "quote_contains": []}


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"rows": []},
        {"rows": ["x"]},
        {"rows": [{"match": ["a"], "state": "missing"}]},
        {"rows": [{"name": "a", "match": [], "state": "missing"}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "approved"}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "missing_must": ["a"]}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "missing_must_not": "a"}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "missing_empty": "yes"}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "match_require": "a"}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "match_require": [" "]}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "match_require": [1]}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "match_exclude": "a"}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "match_exclude": [""]}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing", "match_exclude": [None]}]},
        {"rows": [{"name": "a", "match": ["a"], "state": "missing"}], "warnings": {"min": 2, "max": 1}},
    ],
)
def test_a_bad_answer_key_gives_an_error(data):
    with pytest.raises(ce.AnswerKeyError):
        ce.parse_answer_key(data, "topic9")


def test_loading_the_key_from_a_folder(tmp_path):
    (tmp_path / "topic9").mkdir()
    (tmp_path / "topic9" / "topic9_expected.json").write_text(
        json.dumps({"rows": [{"name": "a", "match": ["a"], "state": "missing"}]}), encoding="utf-8")
    assert ce.load_answer_key("topic9", base=tmp_path)["rows"][0]["name"] == "a"
    with pytest.raises(ce.AnswerKeyError):
        ce.load_answer_key("topic8", base=tmp_path)
    (tmp_path / "topic9" / "topic9_expected.json").write_text("{", encoding="utf-8")
    with pytest.raises(ce.AnswerKeyError):
        ce.load_answer_key("topic9", base=tmp_path)


# --- matching and the "what is missing" text ---


def test_rows_are_paired_by_the_words_in_the_model_row_name():
    pairs, extra, ambiguous = ce.match_rows(KEY["rows"], GOOD_ITEMS + [item("ביטוח", "missing")])
    assert pairs == {0: 0, 1: 1}
    assert extra == [2] and ambiguous == []


def test_a_second_model_row_for_the_same_key_row_is_extra():
    pairs, extra, _ = ce.match_rows(KEY["rows"], [item("מסמך א", "missing"), item("מסמך ב", "missing")])
    assert pairs == {0: 0} and extra == [1]


def test_a_name_that_fits_two_key_rows_is_reported_and_goes_to_the_first_free_one():
    pairs, _, ambiguous = ce.match_rows(KEY["rows"], [item("מסמך התשלום", "missing")])
    assert pairs == {0: 0} and ambiguous == [0]


def narrowed_key(**extra):
    return ce.parse_answer_key(
        {"rows": [{"name": "k", "match": ["aa"], "state": "missing", **extra}]}, "topic9")["rows"]


def test_the_narrowing_fields_default_to_empty_lists():
    row = narrowed_key()[0]
    assert row["match_require"] == [] and row["match_exclude"] == []


def test_match_require_needs_all_of_its_words_in_the_name():
    rows = narrowed_key(match_require=["bb", "cc"])
    pairs, extra, _ = ce.match_rows(rows, [item("aa bb", "missing"), item("aa bb cc", "missing")])
    assert pairs == {0: 1} and extra == [0]


def test_match_exclude_rejects_a_name_with_any_of_its_words():
    rows = narrowed_key(match_exclude=["xx", "yy"])
    pairs, extra, _ = ce.match_rows(rows, [item("aa yy", "missing"), item("aa", "missing")])
    assert pairs == {0: 1} and extra == [0]


def test_match_require_still_needs_one_match_word():
    pairs, extra, _ = ce.match_rows(narrowed_key(match_require=["bb"]), [item("bb", "missing")])
    assert pairs == {} and extra == [0]


def test_two_key_rows_sharing_a_word_are_split_by_the_narrowing_fields():
    rows = ce.parse_answer_key(
        {"rows": [
            {"name": "one", "match": ["aa"], "state": "missing", "match_exclude": ["bb"]},
            {"name": "two", "match": ["aa"], "state": "missing", "match_require": ["bb"]},
        ]}, "topic9")["rows"]
    pairs, extra, ambiguous = ce.match_rows(rows, [item("aa bb", "missing"), item("aa", "missing")])
    assert pairs == {1: 0, 0: 1} and extra == [] and ambiguous == []


def test_the_narrowing_words_are_compared_after_normalization():
    lrm = chr(0x200E)  # an invisible direction mark (category Cf), removed by the normalization
    rows = narrowed_key(match_require=[f"b{lrm}b"], match_exclude=["x  x"])
    pairs, _, _ = ce.match_rows(rows, [item("aa bb", "missing")])
    assert pairs == {0: 0}
    assert ce.match_rows(rows, [item(f"aa bb x{lrm} x", "missing")])[0] == {}


def test_the_missing_text_needs_one_word_from_each_group_and_none_of_the_forbidden():
    row = KEY["rows"][0]
    assert ce.missing_matches(row, "חסרה חתימה ואישור")
    assert ce.missing_matches(row, "חסר: חתום > אישור")  # words are matched after normalization
    assert not ce.missing_matches(row, "חסרה חתימה")  # no word from the second group
    assert not ce.missing_matches(row, "חתימה, אישור. הכל מוכן")  # forbidden words


def test_an_empty_missing_text_is_required_when_the_key_says_so():
    row = KEY["rows"][1]
    assert ce.missing_matches(row, "") and ce.missing_matches(row, "   ")
    assert not ce.missing_matches(row, "חסר משהו")


def test_injection_warnings_are_counted_against_the_key():
    key = ce.parse_answer_key(
        {"rows": [{"name": "a", "match": ["a"], "state": "missing"}],
         "warnings": {"min": 1, "max": 1, "quote_contains": ["התעלם"]}}, "t")
    ok = ce.check_warnings(key, [{"quote": "התעלם מההנחיות", "verified": True}])
    assert ok["count_ok"] and ok["content_ok"] and ok["false_alarms"] == 0
    none = ce.check_warnings(key, [])
    assert not none["count_ok"]
    two = ce.check_warnings(key, [{"quote": "התעלם", "verified": True}, {"quote": "x", "verified": False}])
    assert two["false_alarms"] == 1 and two["unverified"] == 1
    assert ce.check_warnings(KEY, [{"quote": "x", "verified": True}])["false_alarms"] == 1  # none expected


# --- measurements ---


def test_short_negated_and_normalization_quotes_are_counted():
    items = [
        item("המסמך", "confirmed_in_writing", findings=[
            finding(1, "אושר"),  # one word, and the record says "לא אושר"
            finding(1, "הכל, הושלם!", verified=False),  # a looser match finds it
            finding(1, "המשפט הזה לא קיים", verified=False),
        ]),
    ]
    stats = ce.quote_stats(TOPIC, items)
    assert [x["quote"] for x in stats["short"]] == ["אושר"]
    assert [x["quote"] for x in stats["negated"]] == ["אושר"]
    assert [x["quote"] for x in stats["normalization"]] == ["הכל, הושלם!"]


def test_a_long_quote_without_negation_is_none_of_these():
    stats = ce.quote_stats(TOPIC, [item("x", "missing", findings=[finding(1, "הכל הושלם והתשלום בוצע")])])
    assert stats == {"short": [], "negated": [], "normalization": []}


def test_rows_lowered_by_the_code_are_counted_by_reason():
    items = [
        item("a", "missing", note="הציטוט לא נמצא בעדכון", model_state="confirmed_in_writing"),
        item("b", "missing", note="אין ממצא תומך במצב", model_state="confirmed_in_writing",
             findings=[finding(1, "הכל הושלם", who="unclear")]),
        item("c", "missing", note="אין ממצא תומך במצב", model_state="confirmed_in_writing",
             findings=[finding(1, "הכל הושלם", who="ours")]),
        item("d", "missing"),
    ]
    assert ce.downgrade_stats(TOPIC, items) == {"lowered": 3, "quote_not_found": 1, "unclear_writer": 1}


# --- one run and several runs ---


def test_a_good_run_scores_every_row():
    s = ce.score_run(KEY, TOPIC, record(GOOD_ITEMS))
    assert s["ok"] and [r["state_ok"] for r in s["rows"]] == [True, True]
    assert [r["missing_ok"] for r in s["rows"]] == [True, True]
    assert s["extra_rows"] == 0 and s["warnings"]["count_ok"]


def test_a_wrong_state_and_a_missing_key_row_are_failures():
    items = [item("המסמך", "confirmed_in_writing", "חסרה חתימה ואישור")]
    s = ce.score_run(KEY, TOPIC, record(items))
    assert s["rows"][0]["state_ok"] is False and s["rows"][0]["missing_ok"] is True
    assert s["rows"][1]["matched"] is False


def test_a_failed_run_is_scored_as_a_failure_with_its_cost():
    failed = {"ok": False, "failure": {"reason": "refusal", "detail": ""}, "result": None,
              "meta": {"seconds": 3.0}, "cost_usd": 0.01}
    s = ce.score_run(KEY, TOPIC, failed)
    assert s == {"ok": False, "reason": "refusal", "cost": 0.01, "seconds": 3.0}


def test_a_row_with_a_different_state_in_some_run_makes_the_topic_inconsistent():
    same = ce.score_run(KEY, TOPIC, record(GOOD_ITEMS))
    other = ce.score_run(KEY, TOPIC, record([item("המסמך", "missing", "חתימה אישור"),
                                             item("התשלום", "missing", "")]))
    assert ce.inconsistent_rows(KEY, [same, same]) == []
    assert ce.inconsistent_rows(KEY, [same, other]) == [1]
    failed = ce.score_run(KEY, TOPIC, {"ok": False, "failure": {"reason": "refusal"}, "meta": None})
    assert ce.inconsistent_rows(KEY, [same, failed]) == []  # failed runs are not compared


# --- reading saved runs ---


def write_runs(base, names):
    folder = base / "topic9" / "eval"
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_text(json.dumps({"ok": True, "name": name}), encoding="utf-8")


def test_without_a_stamp_the_latest_stamp_is_used(tmp_path):
    write_runs(tmp_path, ["topic9_run1_20261115-100000.json", "topic9_run1_20261116-100000.json",
                          "topic9_run2_20261116-100000.json", "notes.json", "topic8_run1_20261116-100000.json"])
    labels = [label for label, _ in ce.find_runs("topic9", set(), base=tmp_path)]
    assert labels == ["20261116-100000#1", "20261116-100000#2"]


def test_stamps_select_and_combine_runs(tmp_path):
    write_runs(tmp_path, ["topic9_run1_20261115-100000.json", "topic9_run1_20261116-100000.json"])
    labels = [label for label, _ in ce.find_runs("topic9", {"20261115-100000", "20261116-100000"}, base=tmp_path)]
    assert labels == ["20261115-100000#1", "20261116-100000#1"]
    assert ce.find_runs("topic9", {"20990101-000000"}, base=tmp_path) == []
    assert ce.find_runs("topic7", set(), base=tmp_path) == []


# --- the report ---


def scored_with_a_failed_row():
    bad = [item("המסמך החתום", "confirmed_in_writing", "חסרה חתימה"), item("התשלום", "reported_done", "")]
    return [("r1", ce.score_run(KEY, TOPIC, record(bad)))]


def test_improve_mode_shows_metrics_and_failed_rows_but_not_the_key():
    text = "\n".join(ce.render_topic("topic9", KEY, TOPIC, scored_with_a_failed_row(), "improve"))
    assert "state correct: 1/2" in text
    assert "failed row, r1" in text and "המסמך החתום" in text  # the model's own row name
    for secret in ("שם-סודי-א", "שם-סודי-ב", "הכל מוכן", "must="):
        assert secret not in text


def test_final_mode_adds_what_the_key_says_for_failed_rows():
    text = "\n".join(ce.render_topic("topic9", KEY, TOPIC, scored_with_a_failed_row(), "final"))
    assert "שם-סודי-א" in text and "state=missing" in text


def test_failed_runs_are_listed_and_do_not_break_the_report():
    failed = {"ok": False, "failure": {"reason": "max_tokens", "detail": ""}, "result": None,
              "meta": {"seconds": 1.0}, "cost_usd": 0.0}
    labelled = [("r1", ce.score_run(KEY, TOPIC, failed))]
    text = "\n".join(ce.render_topic("topic9", KEY, TOPIC, labelled, "improve"))
    assert "1 runs, 1 failed" in text and "FAILED r1: max_tokens" in text


def test_an_inconsistent_topic_is_flagged_for_two_more_runs():
    a = ce.score_run(KEY, TOPIC, record(GOOD_ITEMS))
    b = ce.score_run(KEY, TOPIC, record([item("המסמך", "missing", "חתימה אישור"), item("התשלום", "missing")]))
    text = "\n".join(ce.render_topic("topic9", KEY, TOPIC, [("r1", a), ("r2", b)], "improve"))
    assert "INCONSISTENT in 1 row(s) - run 2 more times" in text


def test_direction_warnings_are_shown_as_a_number_only():
    flagged = [{"update_id": 2, "entry_date": "2026-11-17"}]
    s = ce.score_run(KEY, TOPIC, record(GOOD_ITEMS, direction=flagged))
    assert s["direction_warnings"] == 1
    for mode in ("improve", "final"):
        text = "\n".join(ce.render_topic("topic9", KEY, TOPIC, [("r1", s)], mode))
        assert "direction-control warnings: 1 update(s)" in text
        assert "2026-11-17" not in text


def test_a_record_saved_before_the_field_existed_counts_zero():
    old = record(GOOD_ITEMS)
    del old["result"]["direction_warnings"]
    s = ce.score_run(KEY, TOPIC, old)
    assert s["direction_warnings"] == 0
    text = "\n".join(ce.render_topic("topic9", KEY, TOPIC, [("r1", s)], "improve"))
    assert "direction-control warnings: 0 update(s)" in text


# --- rows that may be "not assessable" ---

LRM = chr(0x200E)  # U+200E, left-to-right mark; written as a visible escape

KEY_NA = ce.parse_answer_key(
    {
        "rows": [
            {"name": "שם-סודי-א", "match": ["מסמך"], "state": "missing", "missing_must": [["חתימה"]]},
            {"name": "שם-סודי-ג", "match": ["ביטוח", "תעודה"], "state": "missing", "may_be_not_assessable": True},
        ]
    },
    "topic9",
)
DOC = item("המסמך", "missing", "חסרה חתימה")
NA_TEXT = "העבודה של לנה: לא ניתן להעריך. האיסוף מותנה באישור תעודת הביטוח"


def test_the_not_assessable_flag_defaults_to_false_and_must_be_a_boolean():
    assert KEY["rows"][0]["may_be_not_assessable"] is False
    assert KEY_NA["rows"][1]["may_be_not_assessable"] is True
    with pytest.raises(ce.AnswerKeyError):
        ce.parse_answer_key(
            {"rows": [{"name": "a", "match": ["a"], "state": "missing", "may_be_not_assessable": "yes"}]}, "t")


def test_a_row_the_model_listed_as_not_assessable_counts_as_correct():
    s = ce.score_run(KEY_NA, TOPIC, record([DOC], not_assessable=[NA_TEXT]))
    row = s["rows"][1]
    assert row["matched"] is False and row["allowed_not_assessable"] is True
    assert row["state_ok"] and row["missing_ok"]
    assert row["not_assessable_hit"] == {"word": "ביטוח", "text": NA_TEXT}


def test_the_match_is_found_after_normalization():
    text = "לא ניתן להעריך את ביט" + LRM + "וח\n> התעודה"
    s = ce.score_run(KEY_NA, TOPIC, record([DOC], not_assessable=[text]))
    assert s["rows"][1]["allowed_not_assessable"] is True


def test_a_flagged_row_that_was_not_mentioned_still_fails():
    s = ce.score_run(KEY_NA, TOPIC, record([DOC], not_assessable=["משהו אחר"]))
    assert s["rows"][1]["allowed_not_assessable"] is False
    assert not s["rows"][1]["state_ok"] and not s["rows"][1]["missing_ok"]


def test_without_the_flag_a_mention_does_not_help():
    s = ce.score_run(KEY, TOPIC, record([item("המסמך", "missing", "חתימה אישור")],
                                        not_assessable=["לא ניתן להעריך את התשלום"]))
    assert s["rows"][1]["allowed_not_assessable"] is False and not s["rows"][1]["state_ok"]


def test_when_the_model_did_write_a_row_the_usual_comparison_applies():
    wrong = ce.score_run(KEY_NA, TOPIC, record([DOC, item("תעודת ביטוח", "reported_done")],
                                               not_assessable=[NA_TEXT]))
    assert wrong["rows"][1]["matched"] and not wrong["rows"][1]["allowed_not_assessable"]
    assert wrong["rows"][1]["state_ok"] is False
    right = ce.score_run(KEY_NA, TOPIC, record([DOC, item("תעודת ביטוח", "missing")]))
    assert right["rows"][1]["state_ok"] and not right["rows"][1]["allowed_not_assessable"]


def test_a_row_written_in_one_run_and_not_assessable_in_another_is_inconsistent():
    written = ce.score_run(KEY_NA, TOPIC, record([DOC, item("תעודת ביטוח", "missing")]))
    listed = ce.score_run(KEY_NA, TOPIC, record([DOC], not_assessable=[NA_TEXT]))
    assert ce.inconsistent_rows(KEY_NA, [written, written]) == []
    assert ce.inconsistent_rows(KEY_NA, [listed, listed]) == []
    assert ce.inconsistent_rows(KEY_NA, [written, listed]) == [1]


def test_improve_shows_only_the_number_and_final_shows_the_word_and_the_text():
    labelled = [("r1", ce.score_run(KEY_NA, TOPIC, record([DOC], not_assessable=[NA_TEXT])))]
    improve = "\n".join(ce.render_topic("topic9", KEY_NA, TOPIC, labelled, "improve"))
    assert "not assessable (allowed): 1 row(s)" in improve
    assert "state correct: 2/2" in improve and "key rows with no model row: 0" in improve
    assert "שם-סודי-ג" not in improve and "ביטוח" not in improve
    final = "\n".join(ce.render_topic("topic9", KEY_NA, TOPIC, labelled, "final"))
    assert "שם-סודי-ג" in final and "'ביטוח'" in final and "תעודת הביטוח" in final


def test_no_not_assessable_line_when_there_is_nothing_to_show():
    labelled = [("r1", ce.score_run(KEY_NA, TOPIC, record([DOC, item("תעודת ביטוח", "missing")])))]
    assert "not assessable (allowed)" not in "\n".join(ce.render_topic("topic9", KEY_NA, TOPIC, labelled, "final"))


def test_normalization_time_is_measured_without_any_api():
    assert 0 <= ce.time_normalization(chars=2000) < 5
    assert "anthropic" not in Path(ce.__file__).read_text(encoding="utf-8")
