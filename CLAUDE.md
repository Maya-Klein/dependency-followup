# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Planning stage: the repo currently holds only `docs/spec.md` (Hebrew product spec), `docs/plan.md` (approved staged implementation plan) and a Word copy of the spec. There is no code, no git repo and no build/test tooling yet. Read `docs/plan.md` before starting any work; it defines 7 stages and each stage's tests. Work one stage at a time, starting with stage 1 (spec "Gate 1": a feasibility check that saves a deadline and shows it in a colour by days remaining). Stage 2 is a Stitch design of the gate-1 page (a course requirement). Keep anything outside the MVP in the "בהמשך" list in `docs/plan.md`.

The docs are in Hebrew, and the UI is Hebrew with `dir="rtl"`.

## Commands (planned, not yet created)

Stack: Python, Flask + Jinja2, SQLAlchemy Core on SQLite, pytest.

- Run the app: `python run.py`
- Run all tests: `pytest`
- Run one test: `pytest tests/test_deadlines.py::test_name`

Update this section once the real tooling exists.

## Architecture

Three layers, with a one-way dependency, so the UI can be swapped without touching the logic:

- `app/core/`: pure logic with no Flask or DB imports. This includes the deadline arithmetic and the urgency levels (and, from stage 6, the AI analysis).
- `app/storage/`: SQLAlchemy Core tables and repository functions. The connection comes from `DATABASE_URL` (default `sqlite:///data/app.db`), so moving to Postgres should only change that setting.
- `app/web/`: Flask routes and Jinja2 templates. It only calls `core` and `storage`.

The stage-2 Stitch redesign must replace only `web/templates/` and `web/static/`. The existing tests should pass unchanged after it.

## Rules that span files

- **Urgency is computed only in code, never by the AI.** Days remaining and the colour level come from `core/deadlines.py`. AI output (from stage 6) must not change a topic's level.
- **Days are calendar days on a date only, in Israel time (`Asia/Jerusalem`).** Functions take `today` as a parameter so tests are deterministic. On Windows the `tzdata` package is needed.
- **Five levels, thresholds defined once as constants:** `far` (6+ days), `approaching` (2–5), `tomorrow` (1), `today` (0), `overdue` (below 0). A closed topic gets a neutral level and is never overdue (from stage 3).
- **Escaping:** user text (titles, updates, later AI quotes) is rendered through Jinja2 autoescaping. Never use `|safe` on user input. A title containing HTML must be shown as text, and stage 1 has a test for it. A blank title is rejected.
- **Update history is append-only.** Each update or thread is its own dated record and nothing is overwritten. A user-entered summary must be marked as a summary, not a quote. The AI analyses one pasted thread as a whole and does not compare records.
- **No AI component before stage 6.** The model has not been chosen yet.
- **`data/` is git-ignored** (the local SQLite file). In stage 1, add `.gitignore` and run `git init`. Early schema changes may be handled by deleting the local DB.

## כללי עבודה

1. **תכנון לפני ביצוע.** לכל שינוי לא טריוויאלי מציגים תוכנית וממתינים לאישור.
2. **חלוקת מודלים.** תכנון עם Opus, וביצוע וכתיבת קוד עם Sonnet. אם המודל הנוכחי לא מתאים לשלב, להזכיר למשתמש להחליף.
3. **שלבים קטנים.** אף פעם לא בונים את כל הפרויקט בבת אחת.
4. **בדיקות אחרי כל שלב ביצוע.** מריצים בדיקות מקצה לקצה, מקרי קצה ורגרסיה. מדווחים על התוצאות ומתקנים כשלים לפני שממשיכים.
5. **סקירת אבטחה אחרי כל שלב.** בודקים הזרקת קוד, הרשאות, סודות, בדיקת קלט וחשיפת מידע. מדווחים ומציעים תיקונים, ולא מחילים אותם בלי אישור המשתמש.
6. **ענף חדש לכל פיצ'ר,** עם שם תיאורי. אף פעם לא commit ישירות ל-`main`.
7. **commit אחרי כל פעולה שהושלמה,** עם הודעה ברורה.
8. **לוג באובסידיאן.** אחרי כל משימה שהושלמה מוסיפים רשומה קצרה בתיקייה `dependency-followup` בכספת: מה נעשה, החלטות, בעיות פתוחות והצעד הבא.
9. **סודות לא נכנסים ל-commit.** מפתחות API נשמרים ב-`.env`, והוא רשום ב-`.gitignore`.
10. **פשטות וריכוז.** חושבים לפני שכותבים קוד ומציגים הנחות. מעדיפים את הפתרון הפשוט ביותר, עושים שינויים ממוקדים ולא משכתבים קוד שלא קשור.
11. **מקורות.** האפיון ב-`docs/spec.md` והתוכנית ב-`docs/plan.md`. מבצעים רק את השלב הנוכחי בתוכנית.
