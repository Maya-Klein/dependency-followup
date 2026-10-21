[עברית](README.md) | **English**

# Dependency Follow-up Assistant

A tool for tracking topics that are waiting on someone else (a supplier, a colleague, an authority). Each topic has a deadline, and the code computes how many days remain and marks the topic with one of five urgency levels. The UI is in Hebrew, right to left.

The project is built in small stages. Implemented so far: **stage 1 (gate 1)**: saving a deadline and showing it in a colour by days remaining, **stage 2**: the Stitch design, in the templates and the CSS file, and **stage 3**: several topics with a required outcome, a detail page, editing and deletion. The spec is in [`docs/spec.md`](docs/spec.md) and the full plan in [`docs/plan.md`](docs/plan.md) (both in Hebrew).

## Urgency levels

The thresholds are defined once, in `app/core/deadlines.py`. Days are calendar days by date only, in Israel time (`Asia/Jerusalem`).

| Days remaining | Level | Label (shown in the UI) |
|---|---|---|
| 6 or more | `far` | בהמשך (later) |
| 2–5 | `approaching` | מתקרב (approaching) |
| 1 | `tomorrow` | מחר (tomorrow) |
| 0 | `today` | היום (today) |
| below 0 | `overdue` | באיחור (overdue) |

## Architecture

Three layers with a one-way dependency, so the UI can be swapped without touching the logic:

```
web  ──►  core      (pure logic, no Flask and no DB)
 │
 └─────►  storage   (SQLAlchemy Core, SQLite)
```

| Component | Files | Role |
|---|---|---|
| `app/core/` | `deadlines.py` | Days remaining (`days_remaining`), the urgency level (`urgency_level`), the Hebrew wording (`days_text`) and "today" in Israel time (`today_in_israel`). Pure functions that take `today` as a parameter, so tests are deterministic. |
| `app/storage/` | `db.py`, `repository.py` | The `topics` table definition and the `add_topic` and `list_topics` functions. The connection is set by `DATABASE_URL` (default `sqlite:///data/app.db`). An empty title, or one longer than 200 characters, is rejected. |
| `app/web/` | `__init__.py`, `routes.py`, `templates/`, `static/` | The Flask app: `create_app()`, the `GET /` and `POST /` routes, and Jinja2 templates with automatic escaping. |
| `run.py` | | Starts the local server on `127.0.0.1:5000`. |
| `tests/` | | pytest tests for all three layers. |

## Data flow

**Adding a topic (`POST /`):**
1. The form submits a title and a date.
2. The route validates the date and the title length. `add_topic` strips surrounding whitespace and rejects an empty title.
3. The topic is saved in the `topics` table.
4. The browser is redirected to `GET /` (303 redirect). On an error the page comes back with status 400 and a Hebrew message, and the input is kept.

**Showing the list (`GET /`):**
1. `list_topics` fetches the topics sorted by deadline.
2. For each topic, `days_remaining` computes the days remaining against `today_in_israel()`, and `urgency_level` sets the level.
3. The template shows the title, the date, the days wording and a label, with the CSS class `level-<level>`. Colour is not the only carrier of the information, because there is also a text label.

Urgency is computed in code only.

## Installation

Requires Python 3.9 or later (tested only with 3.14).

```
git clone https://github.com/Maya-Klein/dependency-followup.git
cd dependency-followup
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Then set a value for `SECRET_KEY` in `.env` (it is needed for CSRF protection, and the app does not start without it). Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. `.env` is not committed to git. On Linux and macOS use `cp` instead of `copy`.

On Linux and macOS use `.venv/bin/python` instead of `.venv\Scripts\python`. The `tzdata` package is in the list because Windows has no built-in time zone database.

## Running

```
.venv\Scripts\python run.py
```

The app is available at http://127.0.0.1:5000. The DB file is stored in `data/app.db` (not committed to git). You can change it with the `DATABASE_URL` variable.

## Tests

```
.venv\Scripts\python -m pytest
```

The tests cover the boundary values of the levels, month and year transitions, the time zone around midnight, saving and loading from a fresh connection, an empty or too long title, an invalid date, and a title containing HTML code that is shown as text.

## What the app does and does not do

**Does (stages 1–3):**
- Saves a topic with a title, a required outcome and a deadline. All fields are mandatory.
- Computes in code how many days remain (calendar days, Israel time) and marks the topic with one of five levels, with a colour and a text label.
- Shows the list sorted by deadline, with a link to the topic detail page. The title and the outcome are shown as text, even if they contain HTML, and a multi-line outcome keeps its line breaks.
- Lets you edit a topic (title, outcome and deadline) and delete it, after a confirmation page. Deletion is POST-only, and every form is protected by a CSRF token (Flask-WTF).

**Does not (yet):**
- No open/closed status or milestone.
- No update history and no AI analysis of threads.
- No login, multiple users or cloud deployment. A single user on `127.0.0.1`.

## Known limitations

- Days are counted by calendar only, with no working days, weekends or holidays.
- The level thresholds are fixed in the code and cannot be configured.
- Stage 3 added a column (`required_outcome`) to the `topics` table. If you have a `data/app.db` from before stage 3, delete it. Schema changes in the coming stages will require this too.
- `pip-audit` was run on `requirements.txt` (19.10.2026) and found no known vulnerabilities. It is worth running again when dependencies are added.
- The Stitch edge-state and desktop screens were not verified. Only the mobile screen was approved.

## Next steps

According to [`docs/plan.md`](docs/plan.md), one stage at a time:

1. **Stage 4:** a dated update history (including a pasted thread) that is never overwritten, with deletion of an update entered by mistake.
2. **Stage 5:** AI analysis of a thread, isolated and without a UI, with quote verification in code.
3. **Stage 6:** connecting the analysis to the app.
4. **Stage 7:** open/closed status and milestone.
5. **Stage 8:** synthetic scenarios, and gate 3.

The order was changed on 21.10.2026 after lecturer feedback: an AI component is mandatory, so it was moved ahead of status and scenarios.

Ideas outside the MVP are collected in the "בהמשך" (later) section of `docs/plan.md`.

## Design

The design was made in Stitch (project "מעקב תלויות – שער 1 (סופי)", "Dependency tracking – gate 1 (final)") and implemented in stage 2, in the templates and the CSS file only (`app/web/templates/`, `app/web/static/style.css`), without touching `storage/`. In `core/` only two strings changed (the "בהמשך" label and the wording of "יום"). The font is Rubik, hosted locally in `app/web/static/fonts/` (variable font, Hebrew and Latin subsets, OFL licence) rather than loaded from Google Fonts, so the page makes no third-party requests. RTL is complete, corners are 8px, and each topic is a card with a 6px colour stripe on the right.

- **A badge on every level:** colour is not the only signal. All badges have the same width, and their colour intensity grows as the deadline approaches.
- **"Today" versus "overdue":** "today" is a badge with an outline and a clock icon, and "overdue" is a solid red badge with a warning icon. Only these two give the card a coloured background.
- **Mobile:** a single column. The list comes first, and the form opens from the "+ הוספת נושא" (+ add topic) button (`details/summary`, no JavaScript). After an error the form comes back open.
- **Desktop:** a wide list on the right, and the form in a side column, titled "הוספת נושא" (add topic).

Screenshots of the running app (mobile and desktop):

![The app on mobile](docs/design/app-mobile.png)

![The app on desktop](docs/design/app-desktop.png)

The initial design from Stitch was the starting point. In the implementation I changed several things after testing in the browser: a coloured background only for the urgent cards ("today" and "overdue"), badges of uniform width, the label "בהמשך" (later) instead of "far", and on desktop a form in a side column.

![The final mobile screen from Stitch](docs/design/mobile-final.png)

## Development process and tools

- **Model split:** planning with Opus, execution and code writing with Sonnet.
- **Small stages:** one stage at a time, following the plan. A plan for every non-trivial change, and approval before execution.
- **Tests:** end-to-end pytest, edge cases and regression after every stage, and fixing failures before moving on.
- **Security review:** after every stage (injection, input, secrets, information exposure). Findings are reported and fixed only with approval.
- **Git:** a new branch for every feature, never a direct commit to `main`, and a commit after every completed action.
- **Obsidian:** a work log in the vault, in the `dependency-followup` folder. A `Stop` hook (`.claude/settings.json` and `.claude/hooks/log_task.py`) adds a short entry at the end of each round with the branch, commit and a summary. Detailed entries (decisions, open issues, next step) are written by hand.
- **Test hook:** another `Stop` hook (`.claude/hooks/run_tests.py`, registered in `.claude/settings.json`) runs the whole pytest suite at the end of each round, but only if `py`, `html` or `css` files changed since the last green run. A docs-only change does not run the tests. When a test fails, the hook blocks the end of the round and feeds the error back, and it must be fixed before continuing.
- **Stop and alert after 3 failures:** on the third consecutive failure the hook stops blocking and raises an alert: a warning sound different from the usual one, a Windows dialog, a Hebrew message and an entry in the Obsidian log. The alert fires once, and a green run resets the count. The last-run state and the count are kept in `data/.last_tested` and `data/.test_failures` (not committed to git).
- **GitHub CLI (`gh`):** opening and merging pull requests from the terminal.
- **Stitch MCP:** creating the design and the design system directly from Claude Code.
- **Obsidian MCP:** reading and writing the vault from within the session.
- Skills used: frontend-design, security-review
