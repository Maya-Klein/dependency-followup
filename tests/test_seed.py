from datetime import date, timedelta

import pytest

from app.core.deadlines import (
    APPROACHING,
    FAR,
    LEVEL_LABELS,
    OVERDUE,
    TODAY,
    TOMORROW,
    days_remaining,
    urgency_level,
)
from app.storage.repository import (
    USER_SUMMARY,
    add_topic,
    add_update,
    list_topics,
    list_updates,
    normalize_update_text,
)
from app.web import create_app
from scripts import seed as sd
from scripts.eval_topics import load_topic

SCENARIO_TODAY = date(2026, 11, 24)

TITLES = {name: sd.scenario_title(name) for name in sd.SCENARIO_NAMES}

EXPECTED_LEVELS = {
    TITLES["topic1"]: FAR,
    TITLES["topic2"]: FAR,
    TITLES["topic3"]: FAR,
    TITLES["topic4"]: FAR,
    TITLES["topic5"]: OVERDUE,
    TITLES["topic6"]: FAR,
    sd.EXTRA_TOPICS[0][0]: TODAY,
    sd.EXTRA_TOPICS[1][0]: TOMORROW,
    sd.EXTRA_TOPICS[2][0]: APPROACHING,
}


def _by_title(engine):
    return {topic["title"]: topic for topic in list_topics(engine)}


def _levels(engine, today):
    return {
        title: urgency_level(days_remaining(topic["due_date"], today))
        for title, topic in _by_title(engine).items()
    }


def test_loads_the_scenarios_as_written(engine):
    assert sd.seed(engine, SCENARIO_TODAY)

    topics = _by_title(engine)
    assert len(topics) == len(list_topics(engine)) == 9
    for name in sd.SCENARIO_NAMES:
        scenario = load_topic(name)
        assert not TITLES[name].startswith("נושא")
        topic = topics[TITLES[name]]
        assert topic["required_outcome"] == scenario.required_outcome
        stored = sorted(list_updates(engine, topic["id"]), key=lambda u: u["id"])
        assert [(u["entry_date"], u["kind"], u["content"]) for u in stored] == [
            (u.entry_date, u.kind, normalize_update_text(u.content)) for u in scenario.updates
        ]


def test_all_dates_move_by_the_same_shift(engine):
    today = date(2027, 3, 15)

    sd.seed(engine, today)

    topic = _by_title(engine)[TITLES["topic1"]]
    oldest = list_updates(engine, topic["id"])[-1]
    assert oldest["entry_date"] == today - timedelta(days=12)  # 12.11 in the scenario
    assert topic["due_date"] == today + timedelta(days=7)  # 01.12 in the scenario


@pytest.mark.parametrize("today", [SCENARIO_TODAY, date(2027, 3, 15)])
def test_levels_are_the_same_whenever_it_is_loaded(engine, today):
    sd.seed(engine, today)

    assert _levels(engine, today) == EXPECTED_LEVELS
    assert set(EXPECTED_LEVELS.values()) == set(LEVEL_LABELS)


def test_insert_topic_maps_file_numbers_to_database_ids(engine):
    scenario = load_topic("topic3")

    topic_id, update_ids = sd.insert_topic(engine, scenario, "כותרת", timedelta(days=1))

    stored = {u["id"]: u for u in list_updates(engine, topic_id)}
    assert sorted(update_ids) == [u.id for u in scenario.updates]
    for update in scenario.updates:
        assert stored[update_ids[update.id]]["content"] == normalize_update_text(update.content)


def test_a_database_with_topics_is_left_alone(engine):
    topic_id = add_topic(engine, "שלי", SCENARIO_TODAY, "תוצאה")
    add_update(engine, topic_id, USER_SUMMARY, "סיכום", SCENARIO_TODAY)
    before = (list_topics(engine), list_updates(engine, topic_id))

    assert not sd.seed(engine, SCENARIO_TODAY)

    assert (list_topics(engine), list_updates(engine, topic_id)) == before


@pytest.mark.parametrize("value", [None, "", "0", "true"])
def test_main_does_nothing_unless_enabled(tmp_path, monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'seed.db'}")
    if value is None:
        monkeypatch.delenv(sd.ENABLE_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(sd.ENABLE_VARIABLE, value)

    assert sd.main() == 1
    assert not (tmp_path / "seed.db").exists()


def test_main_loads_once_when_enabled(db_url, engine, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv(sd.ENABLE_VARIABLE, "1")

    assert sd.main() == 0
    assert sd.main() == 0

    assert len(list_topics(engine)) == 9
    assert capsys.readouterr().out.splitlines() == [
        "Demo data loaded.",
        "The database already has topics, nothing was loaded.",
    ]


def test_the_app_shows_the_seeded_topics_and_all_levels(db_url, engine, monkeypatch):
    sd.seed(engine, SCENARIO_TODAY)
    monkeypatch.setattr("app.web.routes.today_in_israel", lambda: SCENARIO_TODAY)

    response = create_app(db_url).test_client().get("/")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    for title in EXPECTED_LEVELS:
        assert title in page
    for label in LEVEL_LABELS.values():
        assert label in page
