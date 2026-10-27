import json
import os
import re
import time
import urllib.error
import urllib.request
from types import SimpleNamespace
from tools import (
    AVAILABLE_TOOLS,
    TOOLS_SCHEMA,
    WEATHER_DATA,
    load_data,
    normalize_participants,
    validate_meeting_slot,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")

try:
    from dotenv import load_dotenv as _dotenv_load

    if os.path.exists(ENV_FILE):
        _dotenv_load(dotenv_path=ENV_FILE, override=False)
    else:
        _dotenv_load(override=False)
except ImportError:
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except ImportError:
    class APIStatusError(Exception):
        def __init__(self, message, status_code=500):
            super().__init__(message)
            self.status_code = status_code

    class AuthenticationError(APIStatusError):
        pass

    class RateLimitError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass

    class OpenAI:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def _create(
            self,
            model: str,
            messages: list,
            tools: list = None,
            tool_choice: str = "auto",
            temperature: float = 0.0,
        ):
            serialized_msgs = []
            for m in messages:
                if isinstance(m, dict):
                    serialized_msgs.append(m)
                else:
                    msg_dict = {
                        "role": getattr(m, "role", "assistant"),
                        "content": getattr(m, "content", None),
                    }
                    tcs = getattr(m, "tool_calls", None)
                    if tcs:
                        msg_dict["tool_calls"] = [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tcs
                        ]
                    serialized_msgs.append(msg_dict)

            payload = {
                "model": model,
                "messages": serialized_msgs,
                "temperature": temperature,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                if e.code == 401:
                    raise AuthenticationError(body, status_code=401) from e
                if e.code == 429:
                    raise RateLimitError(body, status_code=429) from e
                raise APIStatusError(body, status_code=e.code) from e
            except urllib.error.URLError as e:
                raise APIConnectionError(str(e)) from e

            raw_msg = resp_data["choices"][0]["message"]
            raw_tcs = raw_msg.get("tool_calls")
            tc_objs = (
                [
                    SimpleNamespace(
                        id=tc["id"],
                        type="function",
                        function=SimpleNamespace(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        ),
                    )
                    for tc in raw_tcs
                ]
                if raw_tcs
                else None
            )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            role=raw_msg.get("role", "assistant"),
                            content=raw_msg.get("content"),
                            tool_calls=tc_objs,
                        )
                    )
                ]
            )


# שמות תצוגה בעברית עבור הכלים, כדי שיומן הפעולות בממשק יהיה ברור למשתמש.
TOOL_HEB_NAMES = {
    "get_weather_forecast": "בדיקת תחזית מזג אוויר (get_weather_forecast)",
    "get_user_calendar": "בדיקת יומן עובד (get_user_calendar)",
    "list_users": "שליפת רשימת עובדים (list_users)",
    "schedule_meeting": "שיבוץ פגישה ביומן (schedule_meeting)",
}

# מילים שמסייעות לזהות אם הבקשה מתייחסת לפעילות בחוץ ולכן רלוונטית לה תחזית מזג האוויר.
OUTDOOR_KEYWORDS = [
    "בחוץ",
    "סיור",
    "קפה",
    "שטח",
    "מזג האוויר",
    "מזג אוויר",
    "ריצה",
    "גינה",
    "פארק",
]


# מתרגם שגיאות נפוצות של OpenAI להודעות ברורות בעברית, כדי להקל על איתור בעיות חיבור או הרשאה.
def explain_openai_error(exc: Exception) -> str:
    """זיהוי מדויק של שגיאות OpenAI לפי סוג החריגה וקוד השגיאה."""
    raw_text = str(exc)
    err_lower = raw_text.lower()

    if isinstance(exc, AuthenticationError):
        return (
            "מפתח ה-API אינו תקין (AuthenticationError 401): בדקי שלא נחתך תו בהעתקה, "
            "שאין מרכאות מיותרות או רווחים בקובץ .env, ושהמפתח מתחיל ב-sk-."
        )

    if isinstance(exc, RateLimitError):
        if (
            "insufficient_quota" in err_lower
            or "credit_balance_exhausted" in err_lower
            or "no credits remaining" in err_lower
            or "exceeded your current quota" in err_lower
        ):
            return (
                "שגיאת מכסה ב-OpenAI (credit_balance_exhausted / insufficient_quota): המפתח תקין, "
                "אבל בחשבון ה-OpenAI אין יתרת קרדיט פעילה (Billing). יש להטעין קרדיט תחת Settings -> Billing."
            )
        return "חריגה ממגבלת בקשות לדקה (RateLimitError 429) מול OpenAI."

    if isinstance(exc, APIStatusError):
        if getattr(exc, "status_code", None) == 404 or "model_not_found" in err_lower:
            return "הפרויקט ב-OpenAI אינו מורשה לגשת למודל המבוקש (404 model_not_found)."
        return f"שגיאת שרת מ-OpenAI (קוד {getattr(exc, 'status_code', 'לא ידוע')}): {raw_text}"

    if isinstance(exc, APIConnectionError):
        return "שגיאת תקשורת / תעודת אבטחה (APIConnectionError) בפנייה ל-api.openai.com."

    return f"שגיאה מ-OpenAI API: {raw_text}"


# מגדיר למודל את תפקיד האג׳נט ואת כללי העבודה שעליו לפעול לפיהם.
def get_system_prompt(current_user: str) -> str:
    """הגדרת המטרה, הכלים והאילוצים של האג'נט."""
    return f"""אתה אג'נט אוטונומי חכם לניהול יומנים ותיאום פגישות בארגון.
המשתמש שמחובר כרגע למערכת הוא: '{current_user}' (חובה לכלול אותו בכל פגישה שהוא יוזם).

הסביבה והאילוצים שלך:
- הימים היחידים הקיימים במערכת הם: 'Sunday', 'Monday', 'Tuesday' (שעות עבודה: '09:00' עד '16:00'). אל תמציא ואל תציע ימים אחרים שאינם קיימים ביומן.
- משבצת זמן נחשבת פנויה אך ורק אם כתוב בה 'פנוי' אצל כל המשתתפים בפגישה באותו יום ובאותה שעה.
- אם הפגישה מתקיימת בחוץ (סיור, בית קפה, שטח), חובה עליך לבדוק באמצעות 'get_weather_forecast' את תחזית מזג האוויר לכל יום שאתה שוקל, לפסול ימים שבהם מזג האוויר גשום או סוער, ולציין בנימוק ('reason') מדוע היום שנפסל לא התאים מבחינת מזג האוויר ומה תחזית מזג האוויר ביום שנבחר.
- כדי להציע מועד לפגישה ולקבל את אישור המשתמש (Human-in-the-Loop), עליך להפעיל את הכלי 'schedule_meeting' ולספק בפרמטר 'reason' נימוק מפורט שמסביר: (א) אילו ימים או שעות נפסלו בגלל התנגשות ביומן או בגלל גשם, ו-(ב) מדוע המועד שנבחר מתאים לכל המשתתפים ולמזג האוויר.
- לעולם אל תסיים את החיפוש אחרי בדיקת יום אחד בלבד אם לא מצאת בו שעה פנויה! חובה לבדוק את כל הימים ('Sunday', 'Monday', 'Tuesday') לפני שמחליטים שאין מועד פנוי.
- אם בדקת את כל 3 הימים ('Sunday', 'Monday', 'Tuesday') ואין אף שעה משותפת שבה כל המשתתפים פנויים, עצור וכתוב למשתמש שאתה מצטער אך אין אף מועד פנוי משותף בשבוע זה, פרט אילו פגישות חוסמות את התיאום, והצע לו לבטל או להזיז משימה חוסמת אם הפגישה קריטית."""


# המחלקה שמנהלת את כל תהליך תיאום הפגישה: שיחה עם המודל, הפעלת כלים, הצעת מועד וקבלת אישור.
class CalendarAgent:
    """
    מנוע האג'נט המרכזי (משמש גם את שרת ה-Web ב-main.py וגם הרצה ישירה מהטרמינל).
    פועל מול OpenAI LLM עם temperature=0 לקבלת החלטות עקבית, מלאה ומנומקת.
    """

    # מאתחל את האג׳נט, את מגבלת צעדי החשיבה ואת מצב ההפעלה.
    def __init__(self, current_user: str = "עמית", max_steps: int = 20):
        self.current_user = current_user
        self.max_steps = max_steps
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.last_api_error = None
        self.last_api_error_heb = None
        self.reset_session(current_user, "")

    # קורא את מפתח ה-API ממשתני הסביבה ומנקה רווחים ומרכאות מיותרות.
    def _get_cleaned_api_key(self) -> str:
        raw_key = os.getenv("OPENAI_API_KEY", "")
        return raw_key.strip().strip('"').strip("'")

    # מנסה ליצור לקוח OpenAI; אם אין מפתח תקין, האג׳נט יוכל לפעול במצב גיבוי מקומי.
    def _init_openai_client(self):
        api_key = self._get_cleaned_api_key()
        if api_key and api_key != "YOUR_API_KEY":
            try:
                return OpenAI(api_key=api_key)
            except Exception as e:
                self.last_api_error = str(e)
                self.last_api_error_heb = explain_openai_error(e)
                return None
        return None

    # מחזיר לממשק מידע על מצב החיבור ועל מצב הפעולה, בלי לחשוף את מפתח ה-API.
    def get_connection_status(self) -> dict:
        """בדיקת סטטוס החיבור ל-OpenAI ללא חשיפת תווים מהמפתח."""
        api_key = self._get_cleaned_api_key()
        has_key = bool(api_key and api_key != "YOUR_API_KEY")

        if not has_key:
            reason_heb = (
                "לא הוגדר משתנה סביבה OPENAI_API_KEY. האג'נט פועל כעת במצב הדגמה מקומי (Fallback). "
                "להפעלה מול OpenAI, הגדירי OPENAI_API_KEY בקובץ .env או במשתני הסביבה."
            )
        elif self.last_api_error_heb:
            reason_heb = self.last_api_error_heb
        else:
            reason_heb = None

        return {
            "openai_configured": has_key,
            "key_status": "מוגדר" if has_key else "לא מוגדר",
            "active_mode": f"OpenAI LLM ({self.model})"
            if (has_key and not self.use_local_brain)
            else "Local Fallback Brain (מצב גיבוי אוטומטי)",
            "model": self.model,
            "last_api_error": self.last_api_error,
            "reason_heb": reason_heb,
        }

    # מאפס את מצב הריצה הקודם ומכין הודעות, יומן צעדים ומשתנים למשימה חדשה.
    def reset_session(self, current_user: str, user_goal: str):
        self.current_user = current_user
        self.user_goal = user_goal
        self.steps_log = []
        self.pending_tool_call = None
        self.step_count = 0
        self.rejected_slots = []
        self.failed_schedule_attempts = 0
        self.meeting_scheduled_successfully = False
        self.nudge_count = 0
        self.last_api_error = None
        self.last_api_error_heb = None
        self.client = self._init_openai_client()
        self.use_local_brain = self.client is None
        self.messages = [
            {"role": "system", "content": get_system_prompt(current_user)},
            {"role": "user", "content": user_goal},
        ]

    # משלים את נימוק ההצעה בפרטים על מזג אוויר, התנגשויות אפשריות ומועדים שנדחו.
    def _enrich_proposal_note(self, func_args: dict, raw_note: str) -> str:
        """
        מוודא שהנימוק שמוצג למשתמש כולל תמיד את כל המידע החשוב:
        1. אם מדובר בפגישת חוץ או שיום Sunday נפסל בגלל גשם – מציין במפורש את בעיית מזג האוויר!
        2. אם השעה המבוקשת במקור הייתה תפוסה או שמועד קודם נדחה – מציין זאת במפורש!
        """
        participants, _, is_outdoor = self._extract_participants_and_title()
        chosen_day = func_args.get("day", "")
        chosen_hour = func_args.get("hour", "")
        notes = []

        # א. בדיקה האם הייתה בעיית מזג אוויר (למשל גשם ביום ראשון בפגישת חוץ)
        sunday_w = WEATHER_DATA.get("Sunday", {})
        chosen_w = WEATHER_DATA.get(chosen_day, {})
        if is_outdoor and chosen_day != "Sunday" and "גשום" in sunday_w.get("condition", ""):
            if "גשום" not in raw_note and "גשם" not in raw_note:
                notes.append(
                    f"🌧️ יום Sunday נפסל מאחר שתחזית מזג האוויר בו היא '{sunday_w.get('condition')}' ({sunday_w.get('temp')}) ואינה מתאימה לפגישת חוץ"
                )

        # ב. בדיקה האם המשתמש ביקש שעה ספציפית שהייתה תפוסה
        preferred_hour_match = re.search(r"(\d{2}:\d{2})", self.user_goal)
        preferred_hour = preferred_hour_match.group(1) if preferred_hour_match else None
        if preferred_hour and preferred_hour != chosen_hour and preferred_hour not in raw_note:
            data = load_data()
            users = data.get("users", {})
            busy_at_pref = [
                f"{p} תפוס ב-'{users.get(p, {}).get('calendar', {}).get(chosen_day, {}).get(preferred_hour, '')}'"
                for p in participants
                if users.get(p, {}).get("calendar", {}).get(chosen_day, {}).get(preferred_hour, "פנוי") != "פנוי"
            ]
            if busy_at_pref:
                notes.append(f"⏰ בשעה המבוקשת ({preferred_hour}) יש התנגשות ({', '.join(busy_at_pref)})")

        # ג. ציון מועדים שנדחו ע"י המשתמש
        if self.rejected_slots:
            notes.append(f"🔄 הוצע מועד חלופי לאחר דחיית המועדים הקודמים ({', '.join(self.rejected_slots)})")

        # ד. הנימוק של המודל עצמו
        clean_raw = (raw_note or "").strip()
        if clean_raw:
            notes.append(clean_raw)
        else:
            notes.append(f"כל המשתתפים ({', '.join(participants)}) פנויים ביום {chosen_day} בשעה {chosen_hour}")

        # ה. הוספת תחזית מזג האוויר של היום שנבחר אם זו פגישת חוץ
        if is_outdoor and chosen_w and chosen_w.get("condition", "") not in " | ".join(notes):
            notes.append(
                f"☀️ מזג האוויר ביום {chosen_day}: {chosen_w.get('condition')} ({chosen_w.get('temp')}) – מתאים לפגישה בחוץ"
            )

        return " | ".join(notes)

    # עוצר לפני שינוי היומנים ושומר את פרטי ההצעה עד שהמשתמש יאשר או ידחה אותה.
    def _pause_for_user_approval(
        self, step_num: int, tool_id: str, func_args: dict, proposal_note: str, is_synthetic: bool = False
    ) -> dict:
        """פונקציה מרכזית אחידה לעצירת הלולאה והצגת כרטיס אישור/דחייה למשתמש."""
        enriched_note = self._enrich_proposal_note(func_args, proposal_note)
        self.pending_tool_call = {
            "id": tool_id,
            "name": "schedule_meeting",
            "args": func_args,
            "note": enriched_note,
            "is_synthetic": is_synthetic,
        }
        self.steps_log.append(
            {
                "step": step_num,
                "type": "approval_needed",
                "title": f"⏸️ צעד #{step_num}: האג'נט מצא מועד פנוי וממתין לאישורך לפני שיבוץ ביומן",
                "tool": "schedule_meeting",
                "args": func_args,
                "result": f"נימוק האג'נט: {enriched_note}",
            }
        )
        return {
            "status": "waiting_approval",
            "pending_meeting": func_args,
            "proposal_note": enriched_note,
            "steps": self.steps_log,
            "mode_info": self.get_connection_status(),
        }

    # מרכז את סיום התהליך ושומר ביומן הפעולות את התשובה הסופית למשתמש.
    def _finish_session(self, step_num: int, final_text: str, status: str = "completed") -> dict:
        """פונקציה מרכזית לסיום ריצת האג'נט והחזרת התשובה הסופית."""
        self.steps_log.append(
            {
                "step": step_num,
                "type": "finish",
                "title": f"✅ תהליך החשיבה הסתיים (צעד #{step_num}) - הודעת האג'נט למשתמש:",
                "details": final_text,
            }
        )
        return {
            "status": status,
            "final_answer": final_text,
            "steps": self.steps_log,
            "mode_info": self.get_connection_status(),
        }

    # שולח בקשה למודל; במקרה של תקלה זמנית מנסה פעם נוספת.
    def _call_openai_with_retry(self):
        """פנייה ל-OpenAI עם temperature=0 (למניעת אקראיות בין הרצות!) וניסיון חוזר אחד במקרה של תקלת רשת."""
        last_exc = None
        for attempt in range(2):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                    temperature=0.0,
                )
            except (AuthenticationError, RateLimitError, APIStatusError) as e:
                raise e
            except Exception as e:
                last_exc = e
                if attempt == 0:
                    time.sleep(0.6)
        raise last_exc

    # נקודת הכניסה למשימה חדשה: איפוס מצב ואז התחלת לולאת האג׳נט.
    def start(self, current_user: str, user_goal: str) -> dict:
        """התחלת משימה חדשה והרצת לולאת האג'נט עד להשלמה או עד לבקשת אישור משתמש."""
        self.reset_session(current_user, user_goal)
        return self.continue_loop()

    # מטפל בהחלטת המשתמש לגבי הצעת הפגישה: אישור לשיבוץ או דחייה ובקשת חלופה.
    def handle_approval(self, approved: bool, reason: str = "") -> dict:
        """טיפול באישור או דחייה של המשתמש (Human-in-the-Loop) והמשך ריצת הלולאה."""
        if not self.pending_tool_call:
            return {
                "status": "error",
                "error": "אין פגישה שממתינה לאישור כרגע.",
                "steps": self.steps_log,
                "mode_info": self.get_connection_status(),
            }

        pending = self.pending_tool_call
        self.pending_tool_call = None
        tool_id = pending["id"]
        func_name = pending["name"]
        func_args = pending["args"]
        is_synthetic = pending.get("is_synthetic", False)

        if approved:
            tool_output = self._execute_tool_safe(func_name, func_args)
            if '"status": "success"' in tool_output:
                self.meeting_scheduled_successfully = True

            self.steps_log.append(
                {
                    "step": self.step_count,
                    "type": "tool",
                    "title": "✅ המשתמש אישר! הפגישה שובצה ביומנים של כל המשתתפים",
                    "tool": func_name,
                    "args": func_args,
                    "result": tool_output,
                }
            )
        else:
            slot_key = f"{func_args.get('day')}_{func_args.get('hour')}"
            if slot_key not in self.rejected_slots:
                self.rejected_slots.append(slot_key)

            # אם המשתמשת כתבה בסיבת הדחייה משהו על חוץ/גשם/מזג אוויר, נוסיף זאת למטרה כדי שייאכף!
            if reason and any(w in reason for w in OUTDOOR_KEYWORDS):
                self.user_goal += f" (דרישת משתמש: {reason})"

            reject_text = reason if reason else "המשתמש ביקש למצוא יום או שעה אחרים."
            tool_output = json.dumps(
                {
                    "status": "rejected_by_user",
                    "message": (
                        f"המשתמש דחה את ההצעה לקבוע ב-{func_args.get('day')} בשעה {func_args.get('hour')}. "
                        f"הערת המשתמש: '{reject_text}'. חובה להתייחס להערת המשתמש, לחפש שעה פנויה אחרת "
                        f"(אסור להציע שוב את {self.rejected_slots}) ולהפעיל את הכלי schedule_meeting עם נימוק מלא!"
                    ),
                },
                ensure_ascii=False,
            )
            self.steps_log.append(
                {
                    "step": self.step_count,
                    "type": "tool",
                    "title": f"❌ המשתמש דחה את ההצעה ({reject_text}) - האג'נט מחפש מועד חלופי...",
                    "tool": func_name,
                    "args": func_args,
                    "result": tool_output,
                }
            )

        if not self.use_local_brain:
            if is_synthetic:
                self.messages.append(
                    {
                        "role": "user",
                        "content": f"עדכון מהמערכת לגבי הצעת הפגישה ({func_args.get('day')} ב-{func_args.get('hour')}): {tool_output}",
                    }
                )
            else:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": tool_output,
                    }
                )

        return self.continue_loop()

    # בודק אילו ימים עדיין לא נבדקו ביומנים, כדי לעזור לאג׳נט לסרוק את כל השבוע הזמין.
    def _get_missing_days_to_scan(self) -> list:
        """בודק אילו ימים מתוך Sunday, Monday, Tuesday טרם נסרקו בלוגים עבור כל המשתתפים."""
        participants, _, _ = self._extract_participants_and_title()
        known_calendars, _ = self._collect_known_state_from_logs(participants)
        missing = []
        for d in ["Sunday", "Monday", "Tuesday"]:
            if not all(d in known_calendars.get(p, {}) for p in participants):
                missing.append(d)
        return missing

    # לולאת העבודה המרכזית: מקבלת החלטה, מפעילה כלים, בוחנת תוצאות וממשיכה או עוצרת.
    def continue_loop(self) -> dict:
        """לולאת האג'נט המרכזית (Reason -> Act -> Observe)."""
        while self.step_count < self.max_steps:
            self.step_count += 1
            step_num = self.step_count

            # --- מסלול א': ריצה מול OpenAI LLM ---
            if self.client and not self.use_local_brain:
                try:
                    response = self._call_openai_with_retry()
                except Exception as api_exc:
                    self.last_api_error = str(api_exc)
                    self.last_api_error_heb = explain_openai_error(api_exc)
                    self.use_local_brain = True
                    print(f"\n[אבחון OpenAI API]: {self.last_api_error_heb}\n")
                    response = None

                if response is not None:
                    message = response.choices[0].message
                    self.messages.append(message)

                    # 1. המודל החזיר תשובת טקסט ללא קריאה לכלי
                    if not message.tool_calls:
                        final_text = (message.content or "המשימה הושלמה.").strip()

                        if not self.meeting_scheduled_successfully:
                            # א. האם כבר קיימת שעה פנויה מוכחת ביומנים שהמודל סרק?
                            free_slot = self._find_common_free_slot_from_logs()
                            if free_slot is not None:
                                if self.nudge_count < 1:
                                    self.nudge_count += 1
                                    self.messages.append(
                                        {
                                            "role": "user",
                                            "content": (
                                                f"מצאת משבצת זמן שבה כל המשתתפים פנויים ({free_slot['day']} בשעה {free_slot['hour']})! "
                                                f"אל תשאל בטקסט – הפעל כעת את הכלי 'schedule_meeting' עם נימוק ב-'reason' כדי להציג למשתמש כפתורי אישור ודחייה."
                                            ),
                                        }
                                    )
                                    continue

                                return self._pause_for_user_approval(
                                    step_num=step_num,
                                    tool_id=f"synth_call_{step_num}",
                                    func_args=free_slot,
                                    proposal_note=final_text,
                                    is_synthetic=True,
                                )

                            # ב. תיקון קריטי: אם המודל ניסה לעצור מוקדם מדי לפני שבדק את כל הימים (Sunday, Monday, Tuesday)!
                            missing_days = self._get_missing_days_to_scan()
                            if missing_days and self.nudge_count < 3:
                                self.nudge_count += 1
                                self.messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            f"עצרת מוקדם מדי! עדיין לא בדקת את היומנים בימים: {', '.join(missing_days)}. "
                                            f"הפעל כעת את 'get_user_calendar' (ואת 'get_weather_forecast' אם זו פגישת חוץ) עבור הימים הללו כדי למצוא מועד פנוי."
                                        ),
                                    }
                                )
                                continue

                            # ג. אם כל 3 הימים נסרקו ובאמת אין אף שעה פנויה (כמו בתרחיש 3 עם אלון) – נחזיר הודעת עצירה מלאה ועקבית!
                            participants, _, _ = self._extract_participants_and_title()
                            return self._finish_session(
                                step_num, self._build_no_slot_message(participants)
                            )

                        return self._finish_session(step_num, final_text)

                    # 2. טיפול בכל הכלים שהמודל ביקש להפעיל (Parallel Tool Calls)
                    valid_schedule_proposal = None
                    for tc in message.tool_calls:
                        func_name = tc.function.name
                        try:
                            func_args = json.loads(tc.function.arguments)
                        except Exception:
                            func_args = {}

                        if valid_schedule_proposal is not None:
                            self.messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": json.dumps(
                                        {"status": "skipped_waiting_for_user_approval"},
                                        ensure_ascii=False,
                                    ),
                                }
                            )
                            continue

                        if func_name == "schedule_meeting":
                            day = func_args.get("day", "")
                            hour = func_args.get("hour", "")
                            reason_arg = func_args.get("reason", "").strip()
                            raw_participants = func_args.get("participants", [])
                            cleaned_participants = normalize_participants(
                                raw_participants, self.current_user
                            )
                            func_args["participants"] = cleaned_participants
                            slot_key = f"{day}_{hour}"
                            _, _, is_outdoor = self._extract_participants_and_title()

                            # חסימה 0 (חדש!): אכיפת מזג אוויר! אם זו פגישת חוץ והמודל ניסה לקבוע ביום גשום (כמו Sunday)
                            day_w = WEATHER_DATA.get(day, {})
                            if is_outdoor and "גשום" in day_w.get("condition", ""):
                                self.failed_schedule_attempts += 1
                                weather_err = json.dumps(
                                    {
                                        "status": "failed",
                                        "reason": (
                                            f"לא ניתן לקבוע פגישת חוץ ביום {day}! תחזית מזג האוויר ליום {day} היא "
                                            f"'{day_w.get('condition')}' ({day_w.get('temp')}) - {day_w.get('recommendation')} "
                                            f"חובה לפסול את יום {day}, לבדוק את הימים האחרים (Monday, Tuesday) שבהם מזג האוויר נאה, "
                                            f"ולציין בנימוק שיום {day} נפסל עקב גשם!"
                                        ),
                                    },
                                    ensure_ascii=False,
                                )
                                self.steps_log.append(
                                    {
                                        "step": step_num,
                                        "type": "tool",
                                        "title": f"🌧️ צעד #{step_num}: נחסם ניסיון לקבוע פגישת חוץ ביום גשום ({day}) - האג'נט בודק יום חלופי",
                                        "tool": func_name,
                                        "args": func_args,
                                        "result": weather_err,
                                    }
                                )
                                self.messages.append(
                                    {"role": "tool", "tool_call_id": tc.id, "content": weather_err}
                                )
                                continue

                            # חסימה 1: בדיקה שהשעה לא נדחתה כבר ע"י המשתמש
                            if slot_key in self.rejected_slots:
                                self.failed_schedule_attempts += 1
                                err_payload = json.dumps(
                                    {
                                        "status": "failed",
                                        "reason": (
                                            f"המועד {day} בשעה {hour} כבר נדחה ע\"י המשתמש! "
                                            f"אסור להציע אותו שוב. מועדים שנדחו: {self.rejected_slots}. "
                                            f"חפש שעה פנויה אחרת (בדוק גם את הימים האחרים אם טרם בדקת) או עצור אם אין שעות פנויות."
                                        ),
                                    },
                                    ensure_ascii=False,
                                )
                                self.steps_log.append(
                                    {
                                        "step": step_num,
                                        "type": "tool",
                                        "title": f"⚠️ צעד #{step_num}: נחסם ניסיון להציע שוב מועד שכבר נדחה ({day} {hour})",
                                        "tool": func_name,
                                        "args": func_args,
                                        "result": err_payload,
                                    }
                                )
                                self.messages.append(
                                    {"role": "tool", "tool_call_id": tc.id, "content": err_payload}
                                )
                                if (
                                    self.failed_schedule_attempts >= 2
                                    and not self._get_missing_days_to_scan()
                                    and self._find_common_free_slot_from_logs() is None
                                ):
                                    stop_summary = self._build_no_slot_message(cleaned_participants)
                                    return self._finish_session(step_num, stop_summary)
                                continue

                            # חסימה 2: בדיקה יבשה שהמועד באמת פנוי אצל כולם לפני שמבקשים אישור
                            is_valid, validation_msg, _ = validate_meeting_slot(
                                cleaned_participants, day, hour, self.current_user
                            )
                            if not is_valid:
                                self.failed_schedule_attempts += 1
                                err_payload = json.dumps(
                                    {
                                        "status": "failed",
                                        "reason": (
                                            f"{validation_msg} "
                                            f"אל תנסה לקבוע בשעה תפוסה! בדוק שעות אחרות או ימים אחרים (Sunday, Monday, Tuesday). "
                                            f"אם בדקת את כל הימים ואין שעה שבה כולם פנויים, עצור והחזר תשובת סיכום למשתמש."
                                        ),
                                    },
                                    ensure_ascii=False,
                                )
                                self.steps_log.append(
                                    {
                                        "step": step_num,
                                        "type": "tool",
                                        "title": f"⚠️ צעד #{step_num}: בדיקת זמינות מנעה הצעת מועד תפוס ({day} {hour})",
                                        "tool": func_name,
                                        "args": func_args,
                                        "result": err_payload,
                                    }
                                )
                                self.messages.append(
                                    {"role": "tool", "tool_call_id": tc.id, "content": err_payload}
                                )
                                if (
                                    self.failed_schedule_attempts >= 2
                                    and not self._get_missing_days_to_scan()
                                    and self._find_common_free_slot_from_logs() is None
                                ):
                                    stop_summary = self._build_no_slot_message(cleaned_participants)
                                    return self._finish_session(step_num, stop_summary)
                                continue

                            # המועד פנוי, לא נדחה, ומתאים למזג האוויר!
                            proposal_note = (
                                reason_arg
                                or (message.content or "").strip()
                                or f"כל המשתתפים ({', '.join(cleaned_participants)}) פנויים ביום {day} בשעה {hour}."
                            )
                            valid_schedule_proposal = (tc.id, func_args, proposal_note)
                            continue

                        # הרצת כלי רגיל (list_users, get_user_calendar, get_weather_forecast)
                        tool_output = self._execute_tool_safe(func_name, func_args)
                        nice_name = TOOL_HEB_NAMES.get(func_name, func_name)
                        self.steps_log.append(
                            {
                                "step": step_num,
                                "type": "tool",
                                "title": f"🔍 צעד #{step_num}: הפעלת כלי - {nice_name}",
                                "tool": func_name,
                                "args": func_args,
                                "result": tool_output,
                            }
                        )
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": tool_output,
                            }
                        )

                    if valid_schedule_proposal is not None:
                        tc_id, f_args, p_note = valid_schedule_proposal
                        return self._pause_for_user_approval(
                            step_num=step_num,
                            tool_id=tc_id,
                            func_args=f_args,
                            proposal_note=p_note,
                            is_synthetic=False,
                        )

                    continue

            # --- מסלול ב': מוח אוטונומי מקומי (Fallback כאשר אין מפתח OpenAI או שיש שגיאת מכסה) ---
            decision = self._local_autonomous_brain()

            if decision["type"] == "final":
                return self._finish_session(step_num, decision["content"])

            func_name = decision["name"]
            func_args = decision["args"]
            proposal_note = decision.get("proposal_note", "")
            tool_call_id = decision.get("id", f"local_call_{step_num}")

            if func_name == "schedule_meeting":
                return self._pause_for_user_approval(
                    step_num=step_num,
                    tool_id=tool_call_id,
                    func_args=func_args,
                    proposal_note=proposal_note,
                    is_synthetic=False,
                )

            tool_output = self._execute_tool_safe(func_name, func_args)
            nice_name = TOOL_HEB_NAMES.get(func_name, func_name)
            self.steps_log.append(
                {
                    "step": step_num,
                    "type": "tool",
                    "title": f"🔍 צעד #{step_num}: הפעלת כלי - {nice_name}",
                    "tool": func_name,
                    "args": func_args,
                    "result": tool_output,
                }
            )

        participants, _, _ = self._extract_participants_and_title()
        fallback_msg = self._build_no_slot_message(participants)
        return self._finish_session(self.step_count, fallback_msg, status="stopped")

    # מפעיל כלי רק אם הוא רשום במערכת, ותופס חריגות כדי להחזיר שגיאה מסודרת במקום לקרוס.
    def _execute_tool_safe(self, func_name: str, func_args: dict) -> str:
        if func_name in AVAILABLE_TOOLS:
            try:
                return AVAILABLE_TOOLS[func_name](**func_args)
            except Exception as e:
                return json.dumps({"error": str(e)}, ensure_ascii=False)
        return json.dumps({"error": f"כלי לא קיים: {func_name}"}, ensure_ascii=False)

    # מחלץ מהבקשה את המשתתפים, את נושא הפגישה ואת השאלה אם מדובר בפעילות בחוץ.
    def _extract_participants_and_title(self) -> tuple:
        all_users = ["עמית", "דני", "יוסי", "אלון"]
        participants = [self.current_user]
        for u in all_users:
            if u in self.user_goal and u not in participants:
                participants.append(u)
        if len(participants) == 1:
            participants.append("דני" if self.current_user != "דני" else "עמית")

        is_outdoor = any(w in self.user_goal for w in OUTDOOR_KEYWORDS)
        title_match = re.search(r"בנושא\s+['\"]?([^.'\"\n]+)['\"]?", self.user_goal)
        if title_match:
            meeting_title = title_match.group(1).strip()
        elif is_outdoor:
            meeting_title = "פגישת סיור בחוץ"
        else:
            meeting_title = "פגישת עבודה"
        return participants, meeting_title, is_outdoor

    # אוסף מתוך תוצאות הכלים שכבר תועדו את היומנים ואת תחזיות מזג האוויר הידועים לאג׳נט.
    def _collect_known_state_from_logs(self, participants: list) -> tuple:
        known_calendars = {p: {} for p in participants}
        known_weather = {}
        for s in self.steps_log:
            if s.get("type") != "tool":
                continue
            if s.get("tool") == "get_user_calendar":
                u = s["args"].get("user_name")
                d = s["args"].get("day")
                try:
                    res = json.loads(s["result"])
                    if u in known_calendars and "schedule" in res:
                        known_calendars[u][d] = res["schedule"]
                except Exception:
                    pass
            elif s.get("tool") == "get_weather_forecast":
                d = s["args"].get("day")
                try:
                    res = json.loads(s["result"])
                    if "forecast" in res:
                        known_weather[d] = res["forecast"]
                except Exception:
                    pass
        return known_calendars, known_weather

    # מחפש מועד פנוי משותף על בסיס מידע שכבר נאסף, בלי לקרוא שוב נתונים שלא נבדקו.
    def _find_common_free_slot_from_logs(self):
        participants, meeting_title, is_outdoor = self._extract_participants_and_title()
        known_calendars, _ = self._collect_known_state_from_logs(participants)

        days_order = ["Sunday", "Monday", "Tuesday"]
        hours_order = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]

        for day in days_order:
            if is_outdoor and "גשום" in WEATHER_DATA.get(day, {}).get("condition", ""):
                continue
            if not all(day in known_calendars[p] for p in participants):
                continue
            for hour in hours_order:
                if f"{day}_{hour}" in self.rejected_slots:
                    continue
                if all(known_calendars[p][day].get(hour) == "פנוי" for p in participants):
                    reason_str = f"כל המשתתפים ({', '.join(participants)}) פנויים ביום {day} בשעה {hour}."
                    return {
                        "participants": participants,
                        "day": day,
                        "hour": hour,
                        "title": meeting_title,
                        "reason": reason_str,
                    }
        return None

    # בונה הודעת סיום עם הסבר כשלא נמצא מועד משותף, ומציע אילו התנגשויות ניתן להזיז.
    def _build_no_slot_message(self, participants: list) -> str:
        """
        בונה הודעת עצירה ברורה ומדויקת כשאין אף מועד פנוי משותף, תוך שימוש בנתוני היומן האמיתיים.
        """
        data = load_data()
        users_data = data.get("users", {})
        days_order = ["Sunday", "Monday", "Tuesday"]
        hours_order = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]

        movable_suggestions = []
        for day in days_order:
            for hour in hours_order:
                others_free = all(
                    users_data.get(p, {}).get("calendar", {}).get(day, {}).get(hour) == "פנוי"
                    for p in participants
                    if p != self.current_user
                )
                my_task = (
                    users_data.get(self.current_user, {})
                    .get("calendar", {})
                    .get(day, {})
                    .get(hour, "")
                )
                if others_free and my_task and my_task != "פנוי":
                    movable_suggestions.append(
                        f"• ביום **{day} בשעה {hour}** שאר המשתתפים פנויים, ואצלך רשום ביומן **'{my_task}'**."
                    )

        if movable_suggestions:
            suggestions_block = (
                "\n\n💡 **משבצות שניתן לפנות אם הפגישה קריטית:**\n"
                + "\n".join(movable_suggestions[:3])
                + "\nאם מדובר בפגישה קריטית, מומלץ לבטל או להזיז את העיסוק הקיים באחת מהשעות הללו ואז לפנות אליי שוב לשיבוץ."
            )
        else:
            suggestions_block = (
                "\n\n💡 **המלצה:** אם מדובר בפגישה קריטית, מומלץ לבטל או להזיז אחת מהפגישות הקיימות ביומן ואז לפנות אליי שוב."
            )

        return (
            f"🛑 **אני מצטער, אך לא נמצא אף מועד פנוי משותף עבור ({', '.join(participants)}).**\n\n"
            f"בדקתי את כל ימי העבודה במערכת (Sunday, Monday, Tuesday) ואין אף שעה שבה כל המשתתפים פנויים בו-זמנית."
            f"{suggestions_block}"
        )

    # מנוע החלטה מקומי חלופי: בוחר את הכלי הבא או מסיים על סמך הנתונים שכבר נאספו.
    def _local_autonomous_brain(self) -> dict:
        """מנוע גיבוי מקומי (Fallback) כאשר אין מפתח OpenAI פעיל."""
        goal = self.user_goal
        participants, meeting_title, is_outdoor = self._extract_participants_and_title()
        known_calendars, known_weather = self._collect_known_state_from_logs(participants)

        for s in reversed(self.steps_log):
            if (
                s.get("type") == "tool"
                and s.get("tool") == "schedule_meeting"
                and '"status": "success"' in s.get("result", "")
            ):
                chosen_day = s["args"].get("day")
                chosen_hour = s["args"].get("hour")
                weather_note = ""
                if is_outdoor and chosen_day in WEATHER_DATA:
                    w_info = WEATHER_DATA[chosen_day]
                    weather_note = f"\n☀️ **תחזית מזג אוויר ליום {chosen_day}:** {w_info.get('condition')} ({w_info.get('temp')}) – מתאים לפגישת חוץ."

                return {
                    "type": "final",
                    "content": (
                        f"✅ **המשימה הושלמה והפגישה שובצה ביומנים!**\n\n"
                        f"📌 **פרטי הפגישה שנקבעה:**\n"
                        f"• **נושא:** {meeting_title}\n"
                        f"• **משתתפים:** {', '.join(participants)}\n"
                        f"• **מועד:** יום {chosen_day} בשעה {chosen_hour}"
                        f"{weather_note}"
                    ),
                }

        days_order = ["Sunday", "Monday", "Tuesday"]
        hours_order = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]

        preferred_hour_match = re.search(r"(\d{2}:\d{2})", goal)
        preferred_hour = preferred_hour_match.group(1) if preferred_hour_match else None
        conflict_notes = []

        for day in days_order:
            if is_outdoor:
                if day not in known_weather:
                    return {
                        "type": "tool",
                        "name": "get_weather_forecast",
                        "args": {"day": day},
                    }
                day_weather = known_weather.get(day, {})
                if "גשום" in day_weather.get("condition", ""):
                    conflict_notes.append(
                        f"יום {day} נפסל בשל מזג אוויר '{day_weather.get('condition')}' ({day_weather.get('temp')})"
                    )
                    continue

            for person in participants:
                if day not in known_calendars[person]:
                    return {
                        "type": "tool",
                        "name": "get_user_calendar",
                        "args": {"user_name": person, "day": day},
                    }

            search_hours = list(hours_order)
            if preferred_hour and preferred_hour in search_hours:
                search_hours.remove(preferred_hour)
                search_hours.insert(0, preferred_hour)

            for hour in search_hours:
                if f"{day}_{hour}" in self.rejected_slots:
                    conflict_notes.append(f"המועד {day} ב-{hour} נדחה ע\"י המשתמש")
                    continue

                busy_people = [
                    f"{p} תפוס ב-'{known_calendars[p][day].get(hour)}'"
                    for p in participants
                    if known_calendars[p][day].get(hour) != "פנוי"
                ]

                if not busy_people:
                    reason_parts = []
                    if conflict_notes:
                        reason_parts.append("לאחר דילוג על אילוצים קודמים (" + " | ".join(conflict_notes[-2:]) + ")")
                    reason_parts.append(f"כל המשתתפים פנויים ביום {day} בשעה {hour}")
                    if is_outdoor and day in known_weather:
                        reason_parts.append(
                            f"מזג האוויר צפוי להיות {known_weather[day].get('condition')} ({known_weather[day].get('temp')})"
                        )
                    reason_str = " | ".join(reason_parts)

                    return {
                        "type": "tool",
                        "name": "schedule_meeting",
                        "args": {
                            "participants": participants,
                            "day": day,
                            "hour": hour,
                            "title": meeting_title,
                            "reason": reason_str,
                        },
                        "proposal_note": reason_str,
                    }
                else:
                    if hour == preferred_hour and day == "Sunday":
                        conflict_notes.append(
                            f"בשעה שביקשת ({day} ב-{hour}): {', '.join(busy_people)}"
                        )

        return {
            "type": "final",
            "content": self._build_no_slot_message(participants),
        }

    # מאפשר להפעיל את האג׳נט דרך שורת הפקודה, בלי להשתמש בממשק ה-Web.
    def run_cli(self, user_goal: str) -> str:
        """הרצת האג'נט באופן אינטראקטיבי מהטרמינל (CLI) - דורש אישור מפורש."""
        print("\n" + "=" * 65)
        print(f"משתמש מחובר: {self.current_user}")
        print(f"מטרה שהתקבלה: {user_goal}")
        status_info = self.get_connection_status()
        print(f"מצב מוח פעיל: {status_info['active_mode']}")
        if status_info.get("reason_heb"):
            print(f"הערת מערכת: {status_info['reason_heb']}")
        print("=" * 65)

        res = self.start(self.current_user, user_goal)

        while res.get("status") == "waiting_approval":
            for s in res.get("steps", []):
                if s.get("type") == "tool":
                    print(f"-> {s['title']}")
                    print(f"   תוצאה: {s['result']}")

            m = res["pending_meeting"]
            print("\n" + "*" * 55)
            print("[בקשת אישור מהמשתמש לפני שינוי ביומן]")
            print(f"  נושא: {m.get('title')}")
            print(f"  יום ושעה: {m.get('day')} בשעה {m.get('hour')}")
            print(f"  משתתפים: {', '.join(m.get('participants', []))}")
            if res.get("proposal_note"):
                print(f"  נימוק האג'נט: {res['proposal_note']}")

            user_confirm = ""
            while not user_confirm:
                user_confirm = input(
                    "האם לאשר את קביעת הפגישה? (כתבי 'כן' לאישור מפורש, או 'לא' / סיבת דחייה): "
                ).strip()
            print("*" * 55 + "\n")

            is_approved = user_confirm.lower() in ["כן", "y", "yes", "אישור", "בטח"]
            res = self.handle_approval(
                approved=is_approved,
                reason="" if is_approved else user_confirm,
            )

        print("\n--- סיכום צעדי האג'נט ---")
        for s in res.get("steps", []):
            print(f"[{s['step']}] {s['title']}")
        print("\nתשובת האג'נט הסופית:")
        print(res.get("final_answer", ""))
        print("=" * 65 + "\n")
        return res.get("final_answer", "")


# מאפשר הרצה ישירה של הקובץ לצורך בדיקה מהטרמינל.
if __name__ == "__main__":
    agent = CalendarAgent(current_user="עמית")
    default_goal = "אני רוצה לקבוע פגישת עבודה עם דני ביום Sunday בשעה 10:00 בנושא תכנון מערכת. אם תפוס, תמצא לנו שעה אחרת שפנויה לשנינו."
    user_input = input("הזיני מטרה לאג'נט (או לחצי Enter לברירת מחדל):\n> ").strip()
    agent.run_cli(user_input if user_input else default_goal)