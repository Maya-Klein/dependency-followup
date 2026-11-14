# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Stage 1 (spec "Gate 1": save a deadline and show it in a colour by days remaining), stage 2 (the Stitch design of the gate-1 page, implemented in the templates and CSS) and stage 3 (several topics: a required outcome, a detail page, edit and delete; the detail screen was designed in Stitch, mobile only) are done and merged to `main` (PRs #1, #5 and #20). Stage 4 (dated updates: a pasted thread or a summary per topic, newest first, delete-only with a confirmation page, a 200,000-character thread limit; the updates area was designed in Stitch, mobile only) is also done and merged to `main` (PR #23). Stage 5 (AI thread analysis) is next. Also planned: a deployment stage (Railway), its place to be decided. On 21.10.2026 the stages were reordered after lecturer feedback that an AI component is mandatory: topics and dated updates (3–4), then AI thread analysis (5–6), then status and milestone (7), then synthetic scenarios (8). The docs are `docs/spec.md` (Hebrew product spec) and `docs/plan.md` (approved staged plan, 8 stages, each with its tests). The final mobile design is in `docs/design/mobile-final.png`. Read `docs/plan.md` before starting any work and work one stage at a time. The Stitch project is "מעקב תלויות – שער 1 (סופי)". Keep anything outside the MVP in the "בהמשך" list in `docs/plan.md`.

The docs are in Hebrew, and the UI is Hebrew with `dir="rtl"`.

Repository: https://github.com/Maya-Klein/dependency-followup (public). Feature work goes through pull requests from a feature branch into `main`.

Obsidian work log: a `Stop` hook (`.claude/settings.json` → `.claude/hooks/log_task.py`) is active. At the end of each turn it appends a short entry (branch, last commit, summary of the last message) to `dependency-followup/יומן עבודה.md` in the vault. It never fails the session. Detailed per-task entries (decisions, open issues, next step) are still written by hand.

## Commands

Stack: Python, Flask + Jinja2 (Flask-WTF for CSRF), SQLAlchemy Core on SQLite, pytest. Use the local venv (`.venv`, git-ignored); setup: `python -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements.txt`.

- First run: copy `.env.example` to `.env` and set `SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`). The app refuses to start without it. Tests set their own key and do not need `.env`.
- Run the app: `.venv\Scripts\python run.py` (http://127.0.0.1:5000)
- Run all tests: `.venv\Scripts\python -m pytest`
- Run one test: `.venv\Scripts\python -m pytest tests/test_deadlines.py::test_name`

`pytest.ini` sets `pythonpath = .`, so tests import `app` directly. The web tests pin "today" by monkeypatching `app.web.routes.today_in_israel`.

## Architecture

Three layers, with a one-way dependency, so the UI can be swapped without touching the logic:

- `app/core/`: pure logic with no Flask or DB imports. This includes the deadline arithmetic and the urgency levels (and, from stage 5, the AI analysis).
- `app/storage/`: SQLAlchemy Core tables and repository functions. The connection comes from `DATABASE_URL` (default `sqlite:///data/app.db`), so moving to Postgres should only change that setting.
- `app/web/`: Flask routes and Jinja2 templates. It only calls `core` and `storage`.

The stage-2 Stitch redesign must replace only `web/templates/` and `web/static/`. The existing tests should pass unchanged after it.

## Rules that span files

- **Urgency is computed only in code, never by the AI.** Days remaining and the colour level come from `core/deadlines.py`. AI output (from stage 5) must not change a topic's level.
- **Days are calendar days on a date only, in Israel time (`Asia/Jerusalem`).** Functions take `today` as a parameter so tests are deterministic. On Windows the `tzdata` package is needed.
- **Five levels, thresholds defined once as constants:** `far` (6+ days), `approaching` (2–5), `tomorrow` (1), `today` (0), `overdue` (below 0). A closed topic gets a neutral level and is never overdue (from stage 7).
- **Escaping:** user text (titles, required outcomes, updates, later AI quotes) is rendered through Jinja2 autoescaping. Never use `|safe` on user input. A title containing HTML must be shown as text, and stage 1 has a test for it. A blank title is rejected.
- **Update history is append-only.** Each update or thread is its own dated record and nothing is overwritten or edited. An update entered by mistake may be deleted (POST only, after a confirmation page), never rewritten. A user-entered summary is marked by the word "סיכום" next to its date, and a pasted thread only by the line at its edge. The AI analyses all of a topic's updates together (each with its date and a source label: correspondence or the user's own summary; approved by the lecturer on 4.11.2026) and does not automatically compare what changed since a previous analysis. The output is one row per component of the required outcome, each in one of five states: confirmed in writing (מאושר בכתב), done per report (בוצע לפי דיווח), missing (חסר), no longer required (לא נדרש עוד), or decided to proceed without full confirmation (הוחלט להתקדם בלי אישור מלא); the spec was updated on 13.11.2026. A user summary is never "confirmed in writing" (proof is only a dated written source from the other side), and every quote is checked in code against the record it came from; both checks are enforced in code, not only in the prompt. If the input exceeds the length limit, the latest updates are taken and the output states what was not read.
- **No AI component before stage 5, which has now started.** The model is `claude-sonnet-5-5` with effort `high`, no fallbacks (see "החלטות שהתקבלו" in `docs/plan.md`). Keep the model name and effort as constants in one place in the code.
- **CSRF:** every POST form includes `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. `SECRET_KEY` comes only from `.env` (git-ignored); never hard-code a fallback. Web tests run with `WTF_CSRF_ENABLED = False`, and the CSRF tests use the `csrf_app` fixture.
- **`data/` is git-ignored** (the local SQLite file). Early schema changes may be handled by deleting the local DB.

## כללי עבודה

1. **תכנון לפני ביצוע.** לכל שינוי לא טריוויאלי מציגים תוכנית וממתינים לאישור. לפני כל תכנון חוקרים את המשתמשת בשאלות (grill me) עד שהדרישות ברורות.
2. **חלוקת מודלים.** תכנון עם Opus, וביצוע וכתיבת קוד עם Sonnet. אם המודל הנוכחי לא מתאים לשלב, להזכיר למשתמש להחליף.
3. **שלבים קטנים.** אף פעם לא בונים את כל הפרויקט בבת אחת.
4. **בדיקות אחרי כל שלב ביצוע.** מריצים בדיקות מקצה לקצה, מקרי קצה ורגרסיה. מדווחים על התוצאות ומתקנים כשלים לפני שממשיכים.
5. **סקירת אבטחה אחרי כל שלב.** בודקים הזרקת קוד, הזרקת פרומפט (prompt injection, במיוחד לקראת שלב ניתוח השרשורים ב-AI), הרשאות, סודות, בדיקת קלט וחשיפת מידע. מדווחים ומציעים תיקונים, ולא מחילים אותם בלי אישור המשתמש.
6. **ענף חדש לכל פיצ'ר,** עם שם תיאורי. אף פעם לא commit ישירות ל-`main`. ב-GitHub פעילה הגנה על `main` (branch protection): מיזוג רק דרך PR, בלי חובת אישור של בודק, וההגנה חלה גם על אדמינים, כך שדחיפה ישירה נדחית.
7. **commit אחרי כל פעולה שהושלמה,** עם הודעה ברורה.
8. **לוג באובסידיאן.** אחרי כל משימה שהושלמה מוסיפים רשומה קצרה בתיקייה `dependency-followup` בכספת: מה נעשה, החלטות, בעיות פתוחות והצעד הבא.
9. **סודות לא נכנסים ל-commit.** מפתחות API נשמרים ב-`.env`, והוא רשום ב-`.gitignore`.
10. **פשטות וריכוז.** חושבים לפני שכותבים קוד ומציגים הנחות. מעדיפים את הפתרון הפשוט ביותר, עושים שינויים ממוקדים ולא משכתבים קוד שלא קשור.
11. **מקורות.** האפיון ב-`docs/spec.md` והתוכנית ב-`docs/plan.md`. מבצעים רק את השלב הנוכחי בתוכנית.
12. **README דו-לשוני.** כל שינוי ב-`README.md` מעודכן גם ב-`README.en.md` (תרגום לאנגלית), באותו commit. בראש שני הקבצים יש קישור לגרסה בשפה השנייה.
13. **עיצוב UX/UI בסטיץ'.** העיצוב נעשה ב-Stitch דרך ה-MCP, ומאושר על ידי המשתמשת לפני מימוש בקוד.
14. **עדכון סעיף הסטטוס.** בסוף כל שלב מעדכנים את סעיף "Project status" ב-`CLAUDE.md`: מה הושלם ומוזג, ומה השלב הבא. בנוסף בודקים שמה שכתוב על השלב ב-`docs/plan.md` תואם את מה שבאמת נעשה, ומתקנים את התוכנית אם יש פער (כלל 15). הבדיקה כוללת גם את שני ה-README (`README.md` ו-`README.en.md`: זהים בתוכן ובמבנה, כל אחד בשפה שלו, כולל הוראות ההתקנה וההרצה) ואת הצילומים ב-`docs/screenshots/`: מוודאים שהם מציגים את המסכים הנוכחיים של האפליקציה האמיתית (נייד ומחשב), ומצלמים מחדש כשמסך השתנה.
15. **שינויים בתוכנית ובאפיון.** כל החלטה שמשנה את התוכנית נרשמת ב-`docs/plan.md`. את `docs/spec.md` משנים רק באישור המשתמשת.
16. **דיווח על סטייה מהתוכנית.** אם צעד מהתוכנית המאושרת לא בוצע או שונה, מדווחים על כך במפורש בסיום, לפני המיזוג.
17. **כש-hook חוסם פקודה.** לא עוקפים אותו בפקודה אחרת. עוצרים, מסבירים מה נחסם ולמה צריך, ומחכים לאישור.
18. **תיקון אי דיוקים במקום.** כשמתגלה אי דיוק בתיעוד (plan.md, spec.md באישור, CLAUDE.md, README), מתקנים אותו מיד באותו ענף, ולא אוספים לעדכון כולל. כלל זה גובר על ההחלטה לעדכן את מסמך התהליך ואת מפת הפרויקט רק בסוף שלב: טעות מתקנים מיד, ותוכן חדש מחכה לסוף השלב.
19. **שמות ענפים.** שם הענף מתאר במילים ספורות את תוכן השינוי, כך שאפשר להבין ממנו מה השתנה בלי לפתוח אותו. ענף אחד לכל שינוי הגיוני אחד. לפני פתיחת ענף מציעים למשתמשת שם וממתינים לאישור.
20. **עותק של hook גלובלי.** אחרי כל שינוי ב-hook גלובלי (`~/.claude/hooks/`) מעדכנים את העותק ב-`docs/global-hooks/`.
21. **מיזוג.** קלוד ממזג בקשת מיזוג רק אחרי אישור מפורש של המשתמשת, ומציג לה לפני כן את הקבצים שהשתנו. אישור למיזוג אחד לא חל על בקשות מיזוג אחרות, אלא אם נאמר במפורש. במיזוג לא מוחקים את הענף, לא במחשב ולא ב-GitHub, עד להחלטה לפני ההגשה.
22. **החלטות הפיכות.** על החלטות שאפשר להחזיר אחורה, כמו שמות של משתנים, פונקציות וקבצים, ניסוח או מבנה קוד פנימי, מחליטים לבד ומדווחים בסוף. שואלים רק על החלטות שאי אפשר להחזיר: מחיקה, שינוי סכמה, שינוי באפיון, מיזוג. כללים 15, 19 ו-21 גוברים על הכלל הזה.
23. **תווים נסתרים בקוד.** תווי כיוון ותווים בלתי נראים אחרים (כמו U+202E, U+200E) לא נכתבים ישירות בקבצים. כותבים אותם כך שיהיו גלויים, למשל `chr(0x202E)` עם הערה. אחרי כתיבה סורקים את הקובץ ובודקים שלא נשאר בו תו מסוג `Cf`. כלי כתיבת הקבצים ממיר escape מסוג backslash-u לתו הממשי, ולכן משתמשים ב-`chr()`.
24. **עריכת קבצים.** שינויים בקבצים קיימים נעשים דרך כלי העריכה כדי שהמשתמשת תראה את השינוי לפני שהוא נשמר. לא משכתבים קבצים דרך סקריפט.
