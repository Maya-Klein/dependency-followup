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


def record(items, warnings=(), direction=()):
    return {
        "ok": True, "failure": None, "cost_usd": 0.02, "meta": {"seconds": 12.5},
        "result": {"items": items, "injection_warnings": list(warnings), "not_assessable": [],
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


def test_normalization_time_is_measured_without_any_api():
    assert 0 <= ce.time_normalization(chars=2000) < 5
    assert "anthropic" not in Path(ce.__file__).read_text(encoding="utf-8")
