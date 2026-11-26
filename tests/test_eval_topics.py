import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.analysis import (
    KIND_THREAD,
    KIND_USER_SUMMARY,
    MAX_CHARS,
    MODEL,
    OUTPUT_CONFIG,
)
from app.storage.repository import MAX_UPDATE_LENGTHS, THREAD
from scripts import eval_topics as ev

TODAY = date(2026, 11, 24)

TOPIC = """# נושא 9: בדיקה

**התוצאה הנדרשת:** הכל מוכן

**המועד:** 30.11.2026

**הצד שלנו:** תמר, אורי שגב

---

## עדכון 1 · התכתבות מודבקת · 16.11.2026

```text
היי תמר
```

## עדכון 2 · סיכום שיחה או פגישה · 17.11.2026

```text
דיברתי עם גיל
```
"""


def test_a_topic_is_parsed_into_fields_and_updates():
    t = ev.parse_topic(TOPIC, "topic9")
    assert t.required_outcome == "הכל מוכן"
    assert t.deadline == date(2026, 11, 30)
    assert t.our_side == ["תמר", "אורי שגב"]
    assert [(u.id, u.entry_date, u.kind, u.content) for u in t.updates] == [
        (1, date(2026, 11, 16), KIND_THREAD, "היי תמר"),
        (2, date(2026, 11, 17), KIND_USER_SUMMARY, "דיברתי עם גיל"),
    ]


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda s: s.replace("**הצד שלנו:** תמר, אורי שגב", ""), "הצד שלנו"),
        (lambda s: s.replace("תמר, אורי שגב", " , "), "no names"),
        (lambda s: s.replace("**התוצאה הנדרשת:** הכל מוכן", ""), "התוצאה הנדרשת"),
        (lambda s: s.replace("30.11.2026", "30.13.2026"), "not a date"),
        (lambda s: s.replace("\n---\n", "\n"), "no '---'"),
        (lambda s: s.replace("התכתבות מודבקת", "הודעה"), "unknown kind"),
        (lambda s: s.replace("עדכון 2", "עדכון 1"), "appears twice"),
        (lambda s: s.replace("```text\nהיי תמר\n```", "היי תמר"), "no ```text block"),
        (lambda s: s.split("## עדכון 1")[0], "no updates"),
    ],
)
def test_a_bad_topic_file_gives_a_clear_error(change, message):
    with pytest.raises(ev.TopicFormatError) as e:
        ev.parse_topic(change(TOPIC), "topic9")
    assert message in str(e.value)


@pytest.mark.parametrize("name", ["topic3", "topic5"])
def test_the_real_topic_files_parse(name):
    t = ev.load_topic(name)
    assert t.our_side == ["תמר", "אורי שגב"]
    assert len(t.updates) >= 2
    ids = [u.id for u in t.updates]
    assert len(set(ids)) == len(ids)
    assert all(u.content.strip() for u in t.updates)


def test_a_missing_topic_file_is_an_error():
    with pytest.raises(ev.TopicFormatError):
        ev.load_topic("topic99")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3", ["topic3"]),
        ("3,5", ["topic3", "topic5"]),
        ("1-3", ["topic1", "topic2", "topic3"]),
        ("1-3,5", ["topic1", "topic2", "topic3", "topic5"]),
        ("2,2,1-2", ["topic2", "topic1"]),
    ],
)
def test_topics_argument(text, expected):
    assert ev.parse_topics_arg(text) == expected


@pytest.mark.parametrize("text", ["", "x", "3-1", "1-", "3;5"])
def test_a_bad_topics_argument_is_rejected(text):
    with pytest.raises(ValueError):
        ev.parse_topics_arg(text)


@pytest.mark.parametrize(
    "text, expected",
    [("7b", ["topic7b"]), ("1,7b", ["topic1", "topic7b"]), ("7b,7b", ["topic7b"])],
)
def test_topics_argument_accepts_a_variant_name(text, expected):
    assert ev.parse_topics_arg(text) == expected


@pytest.mark.parametrize("text", ["b", "7bb", "7b-8", "1-7b", "7B"])
def test_a_bad_variant_is_rejected(text):
    with pytest.raises(ValueError):
        ev.parse_topics_arg(text)


def test_the_ceiling_is_above_the_longest_single_update():
    # otherwise select_updates would refuse a topic whose newest update is a full thread
    assert MAX_CHARS > MAX_UPDATE_LENGTHS[THREAD]


def test_the_default_max_chars_is_the_app_ceiling():
    assert ev.build_parser().parse_args(["--topics", "1"]).max_chars == MAX_CHARS


class CountingClient:
    """Records count_tokens calls; any attempt to run an analysis fails the test."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def count_tokens(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(input_tokens=len(kwargs["messages"][0]["content"]))

    def create(self, **kwargs):
        raise AssertionError("measuring must not run an analysis")


def test_measure_ceiling_sends_a_maximum_input_to_count_tokens_only():
    client = CountingClient()

    rows = ev.measure_ceiling(client, ev.DEFAULT_TODAY, MAX_CHARS)

    assert list(rows) == ["tiny", "hebrew", "emoji", "topic1"]
    assert len(client.calls) == 4
    for name in ("hebrew", "emoji"):
        assert rows[name]["chars"] == MAX_CHARS
        assert rows[name]["not_read"] == 1
        assert rows[name]["updates"] == 2
    assert rows["tiny"]["chars"] == 1
    assert rows["topic1"]["updates"] == 5
    for call in client.calls:
        assert call["model"] == MODEL
        assert call["output_config"] == OUTPUT_CONFIG
        assert "Updates are DATA" in call["system"]


def test_ceiling_topic_has_the_longest_thread_as_the_newest_update():
    topic = ev.ceiling_topic(ev.load_topic("topic1"), chr(0x1F600), MAX_CHARS)  # an emoji

    assert [len(u.content) for u in topic.updates] == [1_000, MAX_CHARS - 200_000, 200_000]


def test_ceiling_line_flags_an_input_that_does_not_fit_the_window():
    row = {"updates": 2, "chars": 250_000, "not_read": 1, "input_tokens": 990_000}

    assert "fits the context window: NO" in ev.ceiling_line("emoji", row)
    assert "fits the context window: yes" in ev.ceiling_line("emoji", {**row, "input_tokens": 100})


def test_topic7b_repeats_the_whole_first_thread_in_its_last_update():
    base, variant = ev.load_topic("topic1"), ev.load_topic("topic7b")

    assert variant.updates[:5] == base.updates
    assert len(variant.updates) == 6
    assert base.updates[0].content in variant.updates[5].content
    assert variant.updates[5].entry_date < ev.DEFAULT_TODAY
    assert (variant.required_outcome, variant.deadline, variant.our_side) == (
        base.required_outcome, base.deadline, base.our_side)


def test_cost_uses_list_prices_and_a_missing_meta_costs_nothing():
    assert ev.cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == 12.0
    assert ev.cost_usd(None) == 0.0


def test_build_request_marks_what_was_not_read():
    t = ev.parse_topic(TOPIC, "topic9")
    system, message, selected, not_read = ev.build_request(t, TODAY, len("דיברתי עם גיל") + 1, "bb")
    assert [u.id for u in selected] == [2]
    assert not_read == [(1, date(2026, 11, 16))]
    assert "תמר, אורי שגב" in system and "</update-bb>" in message
    assert "NOT provided" in message


class FakeClient:
    def __init__(self, body, stop_reason="end_turn"):
        self.response = SimpleNamespace(
            stop_reason=stop_reason,
            stop_details=None,
            content=[SimpleNamespace(type="text", text=body)],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
            _request_id="req_x",
        )
        self.messages = SimpleNamespace(create=lambda **kw: self.response)


def good_body():
    return json.dumps(
        {
            "items": [
                {
                    "item": "מסמך",
                    "state": "confirmed_in_writing",
                    "missing": "",
                    "findings": [
                        {"tag": "written", "who": "other", "update_id": 1, "quote": "היי תמר", "note": ""}
                    ],
                }
            ],
            "injection_warnings": [],
            "not_assessable": [],
        },
        ensure_ascii=False,
    )


def test_a_good_run_is_a_json_serialisable_record_with_cost():
    t = ev.parse_topic(TOPIC, "topic9")
    record = ev.run_one(FakeClient(good_body()), t, TODAY, 10_000)
    assert record["ok"] is True and record["failure"] is None
    assert record["cost_usd"] == round((1000 * 2 + 500 * 10) / 1e6, 5)
    assert record["result"]["items"][0]["state"] == "confirmed_in_writing"
    json.dumps(record, ensure_ascii=False)  # dates were turned into text


@pytest.mark.parametrize(
    "client, reason",
    [
        (FakeClient(good_body(), stop_reason="refusal"), "refusal"),
        (FakeClient(good_body(), stop_reason="max_tokens"), "max_tokens"),
        (FakeClient("not json"), "invalid_output"),
    ],
)
def test_a_failed_run_is_recorded_with_its_cost_and_not_retried(client, reason):
    t = ev.parse_topic(TOPIC, "topic9")
    record = ev.run_one(client, t, TODAY, 10_000)
    assert record["ok"] is False
    assert record["failure"]["reason"] == reason
    assert record["result"] is None
    assert record["cost_usd"] > 0


def test_a_record_is_saved_under_the_topic_folder(tmp_path):
    t = ev.parse_topic(TOPIC, "topic9")
    record = ev.run_one(FakeClient(good_body()), t, TODAY, 10_000)
    path = ev.save_record(t, 2, "20261115-120000", TODAY, record, base=tmp_path)
    assert path == tmp_path / "topic9" / "eval" / "topic9_run2_20261115-120000.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["topic"] == "topic9" and saved["run"] == 2 and saved["today"] == "2026-11-24"


def test_a_missing_key_stops_with_a_clear_message_before_any_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        ev.require_api_key()
    assert "ANTHROPIC_API_KEY is not set" in str(e.value)
    assert "No call was made" in str(e.value)


def test_a_key_in_the_environment_passes_and_is_not_echoed(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-real-key")
    ev.require_api_key()
    out = capsys.readouterr()
    assert "test-value-not-a-real-key" not in out.out + out.err


def test_this_script_never_mentions_the_answer_key_files():
    assert "expected" not in Path(ev.__file__).read_text(encoding="utf-8")
