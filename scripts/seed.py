"""Load the demo data into an empty database: python -m scripts.seed

Meant for the deployed demo, where the database starts empty. It runs only when
SEED_DEMO_DATA=1, it adds nothing to a database that already has a topic, and it
never deletes or changes anything.

Topics 1-6 are the invented stage-5 scenarios, read from their _updates.md files
only. All dates are moved by one shift, so the distances between them stay as in
the scenarios while the urgency levels do not go stale. Dates written inside the
texts are not changed.
"""

import os
import sys
from datetime import timedelta

from dotenv import load_dotenv

from app.core.deadlines import today_in_israel
from app.storage.db import DEFAULT_DATABASE_URL, get_engine
from app.storage.repository import add_topic, add_update, list_topics
from scripts.eval_topics import DEFAULT_TODAY, ROOT, load_topic

ENABLE_VARIABLE = "SEED_DEMO_DATA"

SCENARIO_NAMES = ("topic1", "topic2", "topic3", "topic4", "topic5", "topic6")

# (title, required outcome, days from today): the levels the scenarios do not reach
EXTRA_TOPICS = (
    (
        "טקסט הקיר והתוויות",
        "קובץ סופי ומאושר של טקסט הקיר ושל תוויות העבודות נמצא אצל בית הדפוס.",
        0,
    ),
    (
        "הזמנות לפתיחה",
        "ההזמנה אושרה על ידי כל השותפים ונשלחה לרשימת התפוצה.",
        1,
    ),
    (
        "ביטוח העבודות",
        "אישור כיסוי ביטוחי בכתב לכל העבודות המושאלות, כולל תקופת ההובלה.",
        3,
    ),
)


def scenario_title(name):
    """The first line of the scenario file, without its "topic N:" prefix."""
    path = ROOT / "scripts" / name / f"{name}_updates.md"
    first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
    return first_line.split(":", 1)[1].strip()


def insert_topic(engine, topic, title, shift):
    """Insert a parsed scenario topic with its dates moved by `shift`.

    Returns (topic id, {update number in the file: update id in the database}).
    """
    topic_id = add_topic(engine, title, topic.deadline + shift, topic.required_outcome)
    update_ids = {
        update.id: add_update(engine, topic_id, update.kind, update.content, update.entry_date + shift)
        for update in topic.updates
    }
    return topic_id, update_ids


def seed(engine, today):
    """Returns False, without writing anything, if the database already has a topic."""
    if list_topics(engine):
        return False
    # Read every file before the first write, so a broken file leaves the database empty
    scenarios = [(load_topic(name), scenario_title(name)) for name in SCENARIO_NAMES]
    for topic, title in scenarios:
        insert_topic(engine, topic, title, today - DEFAULT_TODAY)
    for title, required_outcome, days in EXTRA_TOPICS:
        add_topic(engine, title, today + timedelta(days=days), required_outcome)
    return True


def main():
    load_dotenv()  # the same DATABASE_URL the app would use
    # Checked before the database is opened: opening it already creates files and tables
    if os.environ.get(ENABLE_VARIABLE) != "1":
        print(f"{ENABLE_VARIABLE}=1 is not set, nothing was loaded.", file=sys.stderr)
        return 1
    engine = get_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    if seed(engine, today_in_israel()):
        print("Demo data loaded.")
    else:
        print("The database already has topics, nothing was loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
