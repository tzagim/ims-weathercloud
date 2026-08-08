<div dir="rtl">

# IMS + Weathercloud

אינטגרציה אחת ל-Home Assistant שמאחדת שני מקורות מזג אוויר:

- **IMS** (השירות המטאורולוגי)
- **Weathercloud**

אם מוזן מזהה תחנת Weathercloud שלך או של השכנים הנחמדים שלך, הוא ידרוס את הנתונים הרלוונטיים שמתקבלים משירות המטארולוגי. ניתן לראות בהמשך אלו נתונים ידרסו.

אם לא הוזנה תחנת Weathercloud הכל יגיע מ-IMS.

הרכיב הוא עטיפה דקה סביב שתי ספריות PyPI מתוחזקות ([`weatheril`](https://github.com/t0mer/py-weatheril), [`weathercloud`](https://github.com/MauroDruwel/Weathercloud)).

## התקנה (HACS)
### התקנה אוטומטית (מומלץ)
יש ללחוץ על הכפתור הבא (יש לאשר את הוספת המאגר)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&repository=ims-weathercloud&owner=tzagim)

<details>
<summary><strong>התקנה ידנית</strong></summary>

1. HACS ← Integrations ← Menu (⋮) ← **Custom repositories**.
2. יש להדביק את הכתובת ```https://github.com/tzagim/ims-weathercloud```, קטגוריה **Integration**, והוספה.
3. ללחוץ על התקנה

</details>

לאחר הההתקנה יש לבצע **הפעלה מחדש** של Home Assistant.

כאשר המערכת עלתה שוב יש ללחוץ על הכפתור הבא:

[![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)

ללחוץ על "הוספת שילוב" ולחפש את "IMS + Weathercloud".

## הגדרה

- **יישוב** - מציג את היישוב בו נמצאת תחנת ניטור של השירות המטאורולוגי. נבחר מרשימה שנשאבת מ-IMS.
- **שפת נתונים** - עברית / אנגלית.
- **מזהה תחנת Weathercloud** (אופציונלי) - המספר בסוף כתובת התחנה (`app.weathercloud.net/d3930075612` → `3930075612`).
- **שם משתמש + סיסמה** (אופציונלי) - רק לחיישני פנים של תחנה בבעלותך.
- **תדירויות עדכון** - IMS (ברירת מחדל 60 דקות) ו-Weathercloud (ברירת מחדל 10 דקות), ניתנות לשינוי ב-**הגדרות**.

## מאיפה כל חיישן נלקח

השירות המטאורולוגי הוא הבסיס הראשוני עבור כל החיישנים הרלוונטיים.
כאשר מוגדר Weathercloud הוא דורס ערכים נוכחיים ומדווח את הנתונים שלהם.

לכל חיישן יש מאפיין `source` שמראה בזמן ריצה מאיפה הערך הגיע.

| חיישן | מקור | דריסת Weathercloud |
|---|---|---|
| טמפרטורה, מרגיש כמו, לחות, רוח, משב, כיוון רוח, גשם, UV, נקודת טל | IMS | ✅ |
| מהירות/כיוון רוח ממוצעים, לחץ אוויר, עוצמת גשם, קרינה סולארית, חיישני פנים | Weathercloud בלבד | - |
| סיכוי לגשם, PM10, יישוב, מצב נוכחי, תחזית יומית ושעתית | IMS בלבד | - |
| עדכון אחרון IMS / Weathercloud | אבחון | - |

## לוגו
לצורך הלוגו נדרש Home Assistant **2026.3.x** ומעלה.

בגרסאות ישנות יותר לא יוצג אייקון.

# אייקונים מותאמים אישית

ניתן להגדיר באמצעות ההרחבה אייקונים מותאמים אישית, להלן האייקונים שיוצגו:

| | | | |
| - | - | - | - |
| <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/clear-night.svg" width="128"><br>לילה בהיר  | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/cloudy.svg" width="128"><br>מעונן | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/exceptional.svg" width="128"><br>קיצוני | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/fog.svg" width="128"><br>ערפל |
| <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/hail.svg" width="128"><br>ברד | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/lightning.svg" width="128"><br>ברקים | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/partlycloudy.svg" width="128"><br>מעונן חלקית | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/pouring.svg" width="128"><br>גשם שוטף |
| <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/rainy.svg" width="128"><br>גשום | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/snowy-rainy.svg" width="128"><br>גשם ושלג | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/snowy.svg" width="128"><br>מושלג | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/sunny.svg" width="128"><br>שימשי |
| <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/windy-variant.svg" width="128"><br>מעונן ורוחות | <img src="https://raw.githubusercontent.com/tzagim/ims-weathercloud/main/custom_components/ims_weathercloud/weather_icons/windy.svg" width="128"><br>מעונן

לצורך שימוש באפשרות זו ההרחבה ניגשת אל ```http```

## תודות

- [GuyKh](https://github.com/GuyKh) & [t0mer](https://github.com/t0mer).
- [MauroDruwel](https://github.com/MauroDruwel).

שמרו ייחוס למקורות.

</div>
