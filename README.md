# Dependency Follow-up Assistant

כלי למעקב אחר נושאים שממתינים לגורמים אחרים. לכל נושא יש מועד יעד, והקוד מחשב ממנו סימון מדורג לפי הימים שנותרו. האפיון ב-`docs/spec.md` והתוכנית ב-`docs/plan.md`.

## התקנה והרצה

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
```

האפליקציה זמינה ב-http://127.0.0.1:5000. קובץ ה-DB נשמר ב-`data/app.db` (לא עולה לגיט). אפשר לשנות אותו עם המשתנה `DATABASE_URL`.

## בדיקות

```
.venv\Scripts\python -m pytest
```
