# עותק של ה-hook הגלובלי לחסימת פקודות מסוכנות

**העותק הזה הוא לתיעוד בלבד ולא רץ.** ה-hook שפועל בפועל נמצא מחוץ למאגר.

## מה ה-hook עושה
`block_dangerous.py` הוא hook מסוג `PreToolUse` על הכלים Bash ו-PowerShell. הוא קורא את הפקודה לפני הרצתה, ואם היא מסוכנת הוא חוסם אותה ומסביר בעברית למה. הוא חוסם:
- מחיקה רקורסיבית (`rm -r`, `Remove-Item -Recurse`, `rd /s` ועוד), `find ... -delete` ו-`shutil.rmtree`.
- פקודות git שדורסות או מוחקות עבודה: `push --force`, `reset --hard`, `clean`, `checkout .` / `restore .`, ו-`branch -D`.
- פקודות SQL: `DROP TABLE`, `DROP DATABASE` ו-`TRUNCATE`.

הבדיקה היא על טקסט הפקודה בלבד. לכן גם פקודה שרק מזכירה תבנית כזו בתוך טקסט (למשל הודעת commit, או כתיבת קובץ דרך הטרמינל) נחסמת. כתיבת קובץ בכלי Write לא עוברת דרך ה-hook. בכל תקלה בפענוח הקלט ה-hook מאפשר את הפקודה, כדי לא לשבור את הסשן.

## איפה המקור
- ה-hook והבדיקות: `~/.claude/hooks/` (`block_dangerous.py`, `test_block_dangerous.py`).
- ההפעלה: `~/.claude/settings.json`, תחת `hooks.PreToolUse` עם `matcher` של `Bash|PowerShell`.

## עדכון העותק
אחרי כל שינוי ב-hook המקורי מעתיקים את שני הקבצים לכאן (כלל 20 ב-`CLAUDE.md`). בראש הקובץ המקורי יש הערה שמזכירה את זה.

## הרצת הבדיקות
```
python docs/global-hooks/test_block_dangerous.py
```
הבדיקות טוענות את `block_dangerous.py` מאותה תיקייה. הן לא חלק מ-`pytest` של הפרויקט (`testpaths = tests`).
