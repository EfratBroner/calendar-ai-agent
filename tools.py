import copy
import json
import os

# הנתיבים מחושבים ביחס למיקום הקובץ, כדי שהפרויקט יעבוד גם מתיקייה אחרת.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")

# מקור אמת יחיד (Single Source of Truth) לתחזית מזג האוויר המדומה (עבור הכלים ועבור ה-UI)
# תחזית מזג האוויר המדומה שמשמשת את כלי מזג האוויר ואת הממשק.
WEATHER_DATA = {
    "Sunday": {
        "condition": "גשום וסוער",
        "temp": "13°C",
        "icon": "🌧️",
        "recommendation": "לא מתאים לפגישות חוץ או נסיעות, מומלץ לקיים פגישות בזום או בתוך המשרד.",
    },
    "Monday": {
        "condition": "בהיר ונעים",
        "temp": "22°C",
        "icon": "☀️",
        "recommendation": "מזג אוויר מצוין לפגישות פרונטליות, סיורים או פעילות מחוץ למשרד.",
    },
    "Tuesday": {
        "condition": "נאה",
        "temp": "24°C",
        "icon": "🌤️",
        "recommendation": "מזג אוויר נוח לכל סוגי הפגישות.",
    },
}

# נתוני ברירת המחדל: משתמשים, תפקידים, יומנים ופגישות לדוגמה.
INITIAL_DATA = {
    "users": {
        "עמית": {
            "role": "מנהל מוצר",
            "calendar": {
                "Sunday": {
                    "09:00": "פגישת הנהלה",
                    "10:00": "פנוי",
                    "11:00": "פנוי",
                    "12:00": "הפסקת צהריים",
                    "13:00": "אפיון מערכת",
                    "14:00": "פנוי",
                    "15:00": "פגישת לקוח",
                    "16:00": "פנוי",
                },
                "Monday": {
                    "09:00": "פנוי",
                    "10:00": "סקירת קוד",
                    "11:00": "פנוי",
                    "12:00": "הפסקת צהריים",
                    "13:00": "פנוי",
                    "14:00": "ראיון עבודה",
                    "15:00": "פנוי",
                    "16:00": "סיכום יום",
                },
                "Tuesday": {
                    "09:00": "פנוי",
                    "10:00": "פנוי",
                    "11:00": "פגישת תקציב",
                    "12:00": "הפסקת צהריים",
                    "13:00": "פנוי",
                    "14:00": "פנוי",
                    "15:00": "מענה למיילים",
                    "16:00": "פנוי",
                },
            },
        },
        "דני": {
            "role": "מפתח תוכנה",
            "calendar": {
                "Sunday": {
                    "09:00": "דיילי צוות פיתוח",
                    "10:00": "כתיבת קוד",
                    "11:00": "כתיבת קוד",
                    "12:00": "הפסקת צהריים",
                    "13:00": "פנוי",
                    "14:00": "פנוי",
                    "15:00": "בדיקות מערכת",
                    "16:00": "פנוי",
                },
                "Monday": {
                    "09:00": "דיילי צוות פיתוח",
                    "10:00": "סקירת קוד",
                    "11:00": "פנוי",
                    "12:00": "הפסקת צהריים",
                    "13:00": "תיקון באגים",
                    "14:00": "פנוי",
                    "15:00": "פנוי",
                    "16:00": "פנוי",
                },
                "Tuesday": {
                    "09:00": "דיילי צוות פיתוח",
                    "10:00": "פנוי",
                    "11:00": "פיתוח פיצ'ר חדש",
                    "12:00": "הפסקת צהריים",
                    "13:00": "פיתוח פיצ'ר חדש",
                    "14:00": "פנוי",
                    "15:00": "פנוי",
                    "16:00": "הדרכה מקצועית",
                },
            },
        },
        "יוסי": {
            "role": "ארכיטקט מערכת",
            "calendar": {
                "Sunday": {
                    "09:00": "פגישת הנהלה",
                    "10:00": "פנוי",
                    "11:00": "תכנון שרתים",
                    "12:00": "הפסקת צהריים",
                    "13:00": "תכנון שרתים",
                    "14:00": "פנוי",
                    "15:00": "פגישת עבודה (משתתפים: אלון, יוסי)",
                    "16:00": "שיחה עם ספק ענן",
                },
                "Monday": {
                    "09:00": "פנוי",
                    "10:00": "סקירת קוד",
                    "11:00": "פגישת אבטחת מידע",
                    "12:00": "הפסקת צהריים",
                    "13:00": "פנוי",
                    "14:00": "פנוי",
                    "15:00": "פנוי",
                    "16:00": "סיכום יום",
                },
                "Tuesday": {
                    "09:00": "כנס טכנולוגי",
                    "10:00": "כנס טכנולוגי",
                    "11:00": "כנס טכנולוגי",
                    "12:00": "הפסקת צהריים",
                    "13:00": "פנוי",
                    "14:00": "פנוי",
                    "15:00": "פנוי",
                    "16:00": "פנוי",
                },
            },
        },
        "אלון": {
            "role": 'סמנכ"ל טכנולוגיות (יומן עמוס)',
            "calendar": {
                "Sunday": {
                    "09:00": "פגישת דירקטוריון",
                    "10:00": "פגישת דירקטוריון",
                    "11:00": "פגישת משקיעים",
                    "12:00": "פגישת משקיעים",
                    "13:00": "פנוי",
                    "14:00": "ראיון בכירים",
                    "15:00": "פגישת עבודה (משתתפים: אלון, יוסי)",
                    "16:00": 'טיסה לחו"ל',
                },
                "Monday": {
                    "09:00": 'כנס בחו"ל',
                    "10:00": 'כנס בחו"ל',
                    "11:00": 'כנס בחו"ל',
                    "12:00": 'כנס בחו"ל',
                    "13:00": 'כנס בחו"ל',
                    "14:00": 'כנס בחו"ל',
                    "15:00": 'כנס בחו"ל',
                    "16:00": 'כנס בחו"ל',
                },
                "Tuesday": {
                    "09:00": 'כנס בחו"ל',
                    "10:00": 'כנס בחו"ל',
                    "11:00": 'כנס בחו"ל',
                    "12:00": 'כנס בחו"ל',
                    "13:00": 'כנס בחו"ל',
                    "14:00": 'כנס בחו"ל',
                    "15:00": 'כנס בחו"ל',
                    "16:00": 'כנס בחו"ל',
                },
            },
        },
    }
}


# טוען את מצב היומנים מהקובץ; אם הקובץ עדיין לא קיים, יוצר אותו מנתוני ברירת המחדל.
def load_data() -> dict:
    """טעינת נתוני היומנים מקובץ ה-JSON (או אתחול אוטומטי אם הקובץ חסר)."""
    try:
        if not os.path.exists(DATA_FILE):
            save_data(INITIAL_DATA)
            return copy.deepcopy(INITIAL_DATA)
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": f"שגיאה בקריאת קובץ הנתונים: {str(e)}"}


# שומר את מצב הנתונים המעודכן לקובץ JSON ומחזיר אם השמירה הצליחה.
def save_data(data: dict) -> bool:
    """שמירת נתוני היומנים המעודכנים לקובץ ה-JSON."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# מחזיר את היומנים למצב ההתחלתי כדי שאפשר יהיה להדגים שוב את אותם תרחישים.
def reset_data() -> dict:
    """איפוס כל היומנים למצב ההתחלתי הנקי לצורך בדיקה חוזרת של התרחישים."""
    clean_copy = copy.deepcopy(INITIAL_DATA)
    save_data(clean_copy)
    return clean_copy


# מסיר משתתפים כפולים וריקים ושומר על סדר הרשימה; אפשר להוסיף גם את המשתמש היוזם.
def normalize_participants(participants: list, current_user: str = None) -> list:
    """מנקה כפילויות ושומר על סדר המשתתפים, תוך וידוא שהמשתמש היוזם כלול."""
    cleaned = []
    if current_user:
        cleaned.append(current_user)
    if isinstance(participants, list):
        for p in participants:
            if isinstance(p, str):
                p_clean = p.strip()
                if p_clean and p_clean not in cleaned:
                    cleaned.append(p_clean)
    return cleaned


# בודק מראש אם המשתתפים קיימים, אם היום והשעה תקינים ואם כולם פנויים.
def validate_meeting_slot(
    participants: list, day: str, hour: str, current_user: str = None
) -> tuple:
    """
    בדיקה יבשה (Dry-Run Validation) של תקינות וזמינות המועד לפני שמבקשים אישור מהמשתמש
    ולפני ששומרים ביומן. מחזירה: (is_valid: bool, message: str, cleaned_participants: list).
    """
    data = load_data()
    if "error" in data:
        return False, data["error"], []

    # קודם מאחדים את רשימת המשתתפים, כדי לבדוק ולשבץ את אותה רשימה בדיוק.
    cleaned_participants = normalize_participants(participants, current_user)
    if len(cleaned_participants) < 2:
        return (
            False,
            "חובה לציין לפחות שני משתתפים לפגישה (המשתמש היוזם ולפחות עמית נוסף אחד).",
            cleaned_participants,
        )

    users = data.get("users", {})
    busy_details = []

    # כל משתתף נבדק בנפרד: קיום במערכת, יום ושעה תקינים, וזמינות בפועל.
    for person in cleaned_participants:
        if person not in users:
            return (
                False,
                f"המשתמש '{person}' לא קיים במערכת. משתמשים קיימים: {list(users.keys())}",
                cleaned_participants,
            )
        cal = users[person].get("calendar", {})
        if day not in cal:
            return (
                False,
                f"היום '{day}' אינו קיים במערכת. הימים הקיימים בלבד הם: {list(cal.keys())}.",
                cleaned_participants,
            )
        if hour not in cal[day]:
            return (
                False,
                f"השעה '{hour}' אינה בשעות העבודה (09:00 עד 16:00).",
                cleaned_participants,
            )
        slot_status = cal[day][hour]
        if slot_status != "פנוי":
            busy_details.append(f"{person} תפוס ב-'{slot_status}'")

    if busy_details:
        return (
            False,
            f"לא ניתן לקבוע ביום {day} בשעה {hour}! נמצאה התנגשות ביומן: {', '.join(busy_details)}.",
            cleaned_participants,
        )

    return True, "המועד פנוי לכל המשתתפים.", cleaned_participants


# כלי שמחזיר את שמות העובדים ואת התפקידים שלהם בפורמט JSON.
def list_users() -> str:
    """כלי 1: מחזיר את רשימת כל העובדים במערכת והתפקיד שלהם."""
    data = load_data()
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)

    users_info = {
        name: info.get("role", "") for name, info in data.get("users", {}).items()
    }
    return json.dumps({"users": users_info}, ensure_ascii=False)


# כלי שמחזיר את היומן של עובד מסוים ביום המבוקש, או הודעת שגיאה אם הפרטים לא תקינים.
def get_user_calendar(user_name: str, day: str) -> str:
    """כלי 2: מחזיר את לוח הזמנים המלא של משתמש מסוים ביום מבוקש."""
    data = load_data()
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)

    users = data.get("users", {})
    if user_name not in users:
        return json.dumps(
            {
                "error": f"המשתמש '{user_name}' לא נמצא. משתמשים קיימים: {list(users.keys())}"
            },
            ensure_ascii=False,
        )

    calendar = users[user_name].get("calendar", {})
    if day not in calendar:
        return json.dumps(
            {
                "error": f"היום '{day}' לא קיים ביומן. ימים זמינים במערכת: {list(calendar.keys())}"
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"user": user_name, "day": day, "schedule": calendar[day]}, ensure_ascii=False
    )


# כלי שמחזיר תחזית מדומה ליום מסוים; הנתונים אינם תחזית חיה מהאינטרנט.
def get_weather_forecast(day: str) -> str:
    """כלי 3: בודק את תחזית מזג האוויר (נתוני הדגמה מדומים) ליום מסוים."""
    if day not in WEATHER_DATA:
        return json.dumps(
            {"error": f"אין תחזית ליום {day}. ימים זמינים: {list(WEATHER_DATA.keys())}"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"day": day, "simulated": True, "forecast": WEATHER_DATA[day]},
        ensure_ascii=False,
    )


# כלי השיבוץ: מאמת שוב את המועד, מעדכן את יומני כל המשתתפים ושומר את הנתונים.
def schedule_meeting(
    participants: list, day: str, hour: str, title: str, reason: str = ""
) -> str:
    """כלי 4: קובע פגישה משותפת ביומנים של כל המשתתפים, רק לאחר אימות מלא שכולם פנויים."""
    is_valid, validation_msg, cleaned_participants = validate_meeting_slot(
        participants, day, hour
    )
    if not is_valid:
        return json.dumps(
            {"status": "failed", "reason": validation_msg},
            ensure_ascii=False,
        )

    data = load_data()
    users = data.get("users", {})
    clean_title = (title or "פגישת עבודה").strip()
    participants_str = ", ".join(cleaned_participants)
    full_title = f"{clean_title} (משתתפים: {participants_str})"

    # לאחר שהבדיקה הצליחה, רושמים את אותה פגישה בכל היומנים של המשתתפים.
    for person in cleaned_participants:
        users[person]["calendar"][day][hour] = full_title

    if save_data(data):
        return json.dumps(
            {
                "status": "success",
                "message": f"הפגישה '{clean_title}' נקבעה בהצלחה ביום {day} בשעה {hour} עבור: {participants_str}.",
                "reason": reason,
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"status": "failed", "reason": "שגיאה בשמירת הנתונים לקובץ."},
        ensure_ascii=False,
    )


# תיאור הכלים והפרמטרים שלהם בפורמט ש-OpenAI Function Calling מצפה לקבל.
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_users",
            "description": "מחזיר את רשימת כל העובדים הקיימים במערכת והתפקיד שלהם.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_calendar",
            "description": "שליפת לוח הזמנים של משתמש מסוים עבור יום ספציפי (Sunday, Monday, או Tuesday בלבד).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {
                        "type": "string",
                        "description": "שם המשתמש בעברית (למשל 'עמית', 'דני', 'יוסי', 'אלון')",
                    },
                    "day": {
                        "type": "string",
                        "enum": ["Sunday", "Monday", "Tuesday"],
                        "description": "שם היום באנגלית: 'Sunday', 'Monday', או 'Tuesday'",
                    },
                },
                "required": ["user_name", "day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "בדיקת תחזית מזג האוויר (נתוני הדגמה) ליום מסוים ('Sunday', 'Monday', 'Tuesday'). יש להפעיל כאשר הפגישה מתקיימת בחוץ, בסיור או בבית קפה.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": ["Sunday", "Monday", "Tuesday"],
                        "description": "שם היום באנגלית: 'Sunday', 'Monday', או 'Tuesday'",
                    }
                },
                "required": ["day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_meeting",
            "description": (
                "כלי להצעה ושיבוץ של פגישה ביומן עבור רשימת משתתפים ביום ובשעה שבהם כולם רשומים כ-'פנוי'. "
                "המערכת תעצור אוטומטית ותציג למשתמש כפתורי אישור/דחייה עם הנימוק שלך לפני השמירה ביומן."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "רשימת כל המשתתפים בפגישה (חובה לכלול את המשתמש היוזם ולפחות משתתף נוסף), למשל ['עמית', 'דני']",
                    },
                    "day": {
                        "type": "string",
                        "enum": ["Sunday", "Monday", "Tuesday"],
                        "description": "שם היום באנגלית: 'Sunday', 'Monday', או 'Tuesday'",
                    },
                    "hour": {
                        "type": "string",
                        "enum": [
                            "09:00",
                            "10:00",
                            "11:00",
                            "12:00",
                            "13:00",
                            "14:00",
                            "15:00",
                            "16:00",
                        ],
                        "description": "השעה בפורמט HH:MM שבה כל המשתתפים פנויים",
                    },
                    "title": {
                        "type": "string",
                        "description": "נושא הפגישה",
                    },
                    "reason": {
                        "type": "string",
                        "description": "נימוק קצר וברור למשתמש מדוע נבחרה משבצת זמן זו (למשל: 'בשעה 10:00 דני תפוס בכתיבת קוד, אך בשעה 14:00 שניכם פנויים').",
                    },
                },
                "required": ["participants", "day", "hour", "title", "reason"],
            },
        },
    },
]

# מיפוי בין שם הכלי שהמודל מבקש להפעיל לבין פונקציית Python שמבצעת אותו בפועל.
AVAILABLE_TOOLS = {
    "list_users": list_users,
    "get_user_calendar": get_user_calendar,
    "get_weather_forecast": get_weather_forecast,
    "schedule_meeting": schedule_meeting,
}