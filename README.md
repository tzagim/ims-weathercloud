<div dir="rtl">

# IMS + Weathercloud

אינטגרציה אחת ל-Home Assistant שמאחדת שני מקורות מזג אוויר:

- **IMS** (השירות המטאורולוגי)
- **Weathercloud**

אם מוזן מזהה תחנת Weathercloud שלך או של השכנים הנחמדים שלך, זה ידרוס את הנתונים הרלוונטיים שמתקבלים משירות המטארולוגי.

אם לא הוזנה תחנת Weathercloud הכל מגיע מ-IMS.

הרכיב הוא עטיפה דקה סביב שתי ספריות PyPI מתוחזקות (`weatheril`, `weathercloud`).

## התקנה (HACS)
### התקנה אוטומטית (מומלץ)
יש ללחוץ על הפתור הבא (יש לאשר את הוספת המאגר)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&repository=ims-weathercloud&owner=tzagim)

### התקנה ידנית
1. HACS ← Integrations ← Menu (⋮) ← **Custom repositories**.
2. יש להדביק את הכתובת ```https://github.com/tzagim/ims-weathercloud```, קטגוריה **Integration**, והוספה.
3. ללחוץ על התקנה

### הפעלה
לאחר הההתקנה יש לבצע **הפעלה מחדש** של Home Assistant.

כאשר המערכת עלתה שוב יש ללחוץ על הכפתור הבא:

[![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)

ללחוץ על "הוספת שילוב" ולחפש את "IMS + Weathercloud".

## הגדרה

- **יישוב** - נבחר מרשימה שנשאבת מ-IMS לפי שפת ה-HA שלך.
- **שפת נתונים** - עברית / אנגלית.
- **מזהה תחנת Weathercloud** (אופציונלי) - המספר בסוף כתובת התחנה (`app.weathercloud.net/d3930075612` → `3930075612`).
- **שם משתמש + סיסמה** (אופציונלי) - רק לחיישני פנים של תחנה בבעלותך.
- **תדירויות עדכון** - IMS (ברירת מחדל 60 דקות) ו-Weathercloud (ברירת מחדל 10 דקות), ניתנות לשינוי ב-**הגדרות**.

## מאיפה כל חיישן נלקח

IMS הוא הבסיס תמיד.
Weathercloud דורס ערכים נוכחיים כשהוא מוגדר ומדווח אותם. לכל חיישן יש מאפיין `source` שמראה בזמן ריצה מאיפה הערך הגיע.

| חיישן | מקור | דריסת Weathercloud |
|---|---|---|
| טמפרטורה, מרגיש כמו, לחות, רוח, משב, כיוון רוח, גשם, UV, נקודת טל | IMS | ✅ |
| מהירות/כיוון רוח ממוצעים, לחץ אוויר, עוצמת גשם, קרינה סולארית, חיישני פנים | Weathercloud בלבד | - |
| סיכוי לגשם, PM10, יישוב, מצב נוכחי | IMS בלבד | - |
| תחזית יומית + שעתית | IMS בלבד | - |
| עדכון אחרון IMS / Weathercloud | אבחון | - |

## לוגו

הלוגו כלול בתיקייה `custom_components/ims_weathercloud/brand/`. החל מ-Home Assistant **2026.3**, HA מציג אותו ישירות מהתיקייה. בגרסאות ישנות יותר יוצג אייקון גנרי.

## תודות

- [GuyKh](https://github.com/GuyKh) & [t0mer](https://github.com/t0mer) - [`weatheril`](https://github.com/t0mer/py-weatheril).
- [MauroDruwel](https://github.com/MauroDruwel) - [`weathercloud`](https://github.com/MauroDruwel/Weathercloud).

שמרו ייחוס למקורות.

</div>
