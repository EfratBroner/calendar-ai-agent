import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from agent import CalendarAgent
from tools import WEATHER_DATA, load_data, reset_data

PORT = 8765

# יצירת האג'נט שמשמש את בקשות השרת.
AGENT = CalendarAgent(current_user="עמית")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>אג'נט חכם לניהול יומנים ופגישות</title>
<style>
  body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f6f9; margin: 0; padding: 20px; color: #1e293b; }
  .container { max-width: 1200px; margin: 0 auto; }
  .header { background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; padding: 22px 28px; border-radius: 14px; margin-bottom: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
  .header h1 { margin: 0 0 6px 0; font-size: 24px; }
  .header p { margin: 0; opacity: 0.9; font-size: 14px; }
  .status-badge { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.35); padding: 8px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; }
  .diag-banner { background: #fffbeb; border: 1px solid #f59e0b; color: #92400e; padding: 12px 16px; border-radius: 10px; margin-bottom: 18px; font-size: 13.5px; line-height: 1.5; display: none; }
  .grid { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 20px; }
  .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 20px; }
  h2 { margin-top: 0; font-size: 18px; color: #1e3a8a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
  label { font-weight: 600; display: block; margin-bottom: 6px; font-size: 14px; }
  select, textarea, input[type="text"] { width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-family: inherit; font-size: 14px; box-sizing: border-box; margin-bottom: 12px; }
  .btn { background: #2563eb; color: white; border: none; padding: 11px 20px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 15px; transition: 0.2s; width: 100%; }
  .btn:hover { background: #1d4ed8; }
  .btn-reset { background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12.5px; font-weight: 600; }
  .btn-reset:hover { background: #e2e8f0; }
  .btn-preset { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; margin: 4px 0; width: 100%; text-align: right; padding: 9px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; }
  .btn-preset:hover { background: #dbeafe; }
  .final-summary-card { border: 2px solid #10b981; background: #ecfdf5; padding: 16px; border-radius: 10px; margin-bottom: 14px; display: none; white-space: pre-wrap; line-height: 1.5; font-size: 14px; }
  .step-box { border-right: 4px solid #3b82f6; background: #f8fafc; padding: 12px 14px; border-radius: 8px; margin-bottom: 10px; font-size: 13.5px; }
  .step-box.finish { border-right-color: #10b981; background: #ecfdf5; }
  .step-box.approval { border-right-color: #f59e0b; background: #fffbeb; }
  .code-line { font-family: monospace; background: #e2e8f0; padding: 4px 8px; border-radius: 4px; display: block; margin-top: 6px; font-size: 12px; word-break: break-all; }
  .approval-card { border: 2px solid #f59e0b; background: #fef3c7; padding: 16px; border-radius: 10px; margin-top: 12px; margin-bottom: 14px; display: none; box-shadow: 0 4px 12px rgba(245, 158, 11, 0.15); }
  .btn-approve { background: #16a34a; color: white; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; margin-left: 8px; font-size: 14px; }
  .btn-approve:hover { background: #15803d; }
  .btn-reject { background: #dc2626; color: white; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; }
  .btn-reject:hover { background: #b91c1c; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 10px; }
  th, td { border: 1px solid #e2e8f0; padding: 6px 8px; text-align: center; }
  th { background: #f1f5f9; color: #334155; }
  .free-slot { background: #dcfce7; color: #166534; font-weight: 600; }
  .busy-slot { background: #fee2e2; color: #991b1b; }
  .new-meeting { background: #dbeafe; color: #1e40af; font-weight: 700; border: 2px solid #2563eb; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>🤖 אג'נט חכם לניהול יומנים ותיאום פגישות</h1>
      <p>מערכת אוטונומית לקבלת החלטות, בדיקת יומנים ומזג אוויר, אישור משתמש (Human-in-the-Loop) והמלצה על חלופות</p>
    </div>
    <div id="modeBadge" class="status-badge">בודק חיבור מוח אג'נט...</div>
  </div>

  <div id="diagBanner" class="diag-banner"></div>

  <div class="grid">
    <div>
      <div class="card">
        <h2>1. התחברות והגדרת מטרה לאג'נט</h2>
        <label>משתמש מחובר:</label>
        <select id="userSelect" onchange="syncUser()"></select>

        <label>תרחישי בדיקה מוכנים (לחצי על תרחיש כדי למלא אותו):</label>
        <button type="button" class="btn-preset" onclick="setPreset(1)">🎯 תרחיש 1 (פתרון התנגשות + אישור): פגישה עם דני בראשון ב-10:00 (תפוס -> ימצא חלופה)</button>
        <button type="button" class="btn-preset" onclick="setPreset(2)">🌦️ תרחיש 2 (אילוץ מזג אוויר + ריבוי משתתפים): פגישת סיור בחוץ עם דני ויוסי (יפסול יום גשום!)</button>
        <button type="button" class="btn-preset" onclick="setPreset(3)">🛑 תרחיש 3 (תנאי עצירה כשאין מועד פנוי): ניסיון קביעה עם אלון (הלוח מלא -> יעצור ויציע מה לבטל)</button>

        <label style="margin-top:12px;">מטרה חופשית לאג'נט:</label>
        <textarea id="goalInput" rows="3" placeholder="בחרי תרחיש למעלה או הקלידי כאן כל מטרה..."></textarea>
        <button type="button" class="btn" id="runBtn" onclick="startAgent()">🚀 הפעל אג'נט</button>
      </div>

      <div class="card">
        <h2>2. תוצאת האג'נט ותהליך קבלת ההחלטות (Live Log)</h2>

        <div id="approvalBox" class="approval-card">
          <strong style="font-size: 15px;">⚠️ האג'נט מצא מועד פנוי ומבקש את אישורך לפני שיבוץ ביומן:</strong>
          <p id="approvalText" style="margin: 8px 0; font-weight: 700; color: #92400e; font-size: 14.5px;"></p>
          <p id="approvalNote" style="margin: 6px 0 12px 0; font-size: 13.5px; color: #78350f; white-space: pre-wrap;"></p>
          <input type="text" id="rejectReason" placeholder="אם את דוחה - כתבי סיבה (למשל: 'אני מעדיפה ביום שני' או השאירי ריק)" style="margin-bottom:10px;">
          <div>
            <button type="button" class="btn-approve" onclick="sendApproval(true)">✅ אשר ושבץ ביומן</button>
            <button type="button" class="btn-reject" onclick="sendApproval(false)">❌ דחה והצע מועד חלופי אחר</button>
          </div>
        </div>

        <div id="finalSummaryCard" class="final-summary-card"></div>

        <div id="stepsContainer"><p style="color:#64748b;">טרם הופעל אג'נט. בחרי תרחיש ולחצי על "הפעל אג'נט".</p></div>
      </div>
    </div>

    <div>
      <div class="card">
        <h2>
          <span>📅 מצב היומנים ותחזית מזג האוויר (נתוני הדגמה)</span>
          <button type="button" class="btn-reset" onclick="resetCalendars()">🔄 איפוס יומנים למצב התחלתי</button>
        </h2>
        <label>הצג יומן של עובד:</label>
        <select id="viewCalendarUser" onchange="renderCalendars()"></select>
        <div id="calendarTableContainer"></div>
      </div>
    </div>
  </div>
</div>

<script>
let allData = {};
let weatherData = {};

// מטרות לדוגמה שאפשר לטעון בלחיצה.
const PRESETS = {
  1: "אני רוצה לקבוע פגישת עבודה עם דני ביום Sunday בשעה 10:00 בנושא תכנון מערכת. אם תפוס, תמצא לנו שעה אחרת שפנויה לשנינו.",
  2: "אני רוצה לתאם פגישת סיור בחוץ בבית קפה עם דני ויוסי השבוע. חשוב לבדוק גם שכולם פנויים ביומן וגם שמזג האוויר מתאים לישיבה בחוץ!",
  3: "אני חייב לקבוע פגישה עם אלון השבוע בנושא אישור תקציב שנתי. תבדוק את כל הימים ותקבע לנו."
};

// מנקה טקסט לפני שילובו ב-HTML כדי לצמצם סיכון להזרקת קוד.
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setPreset(num) {
  document.getElementById('goalInput').value = PRESETS[num];
}

function syncUser() {
  document.getElementById('viewCalendarUser').value = document.getElementById('userSelect').value;
  renderCalendars();
}

// מציג אם האג'נט משתמש ב-OpenAI או במצב הגיבוי המקומי.
function updateModeBadge(modeInfo) {
  if (!modeInfo) return;
  const badge = document.getElementById('modeBadge');
  const diag = document.getElementById('diagBanner');

  if (modeInfo.openai_configured && !modeInfo.last_api_error) {
    badge.innerText = "🟢 מוח פעיל: " + modeInfo.active_mode + " (מפתח " + modeInfo.key_status + ")";
    diag.style.display = 'none';
  } else {
    badge.innerText = "🟠 מוח פעיל: " + modeInfo.active_mode;
    if (modeInfo.reason_heb) {
      let html = "<strong>🔎 למה האג'נט רץ במצב גיבוי מקומי?</strong><br>" + escapeHtml(modeInfo.reason_heb);
      if (modeInfo.last_api_error) {
        html += '<span class="code-line">פירוט שגיאה טכני מ-OpenAI: ' + escapeHtml(modeInfo.last_api_error) + '</span>';
      }
      diag.innerHTML = html;
      diag.style.display = 'block';
    }
  }
}

// טוען מהשרת את היומנים, התחזית ופרטי מצב החיבור.
async function fetchCalendars() {
  try {
    const res = await fetch('/api/data?t=' + Date.now(), { cache: 'no-store' });
    const payload = await res.json();
    allData = payload.data || payload;
    if (payload.weather) {
      weatherData = payload.weather;
    }
    if (payload.mode_info) {
      updateModeBadge(payload.mode_info);
    }
    const userSelect = document.getElementById('userSelect');
    const viewSelect = document.getElementById('viewCalendarUser');
    if (userSelect.options.length === 0 && allData.users) {
      for (const [name, info] of Object.entries(allData.users)) {
        userSelect.add(new Option(name + " (" + info.role + ")", name));
        viewSelect.add(new Option(name + " (" + info.role + ")", name));
      }
    }
    renderCalendars();
  } catch (err) {
    console.error(err);
  }
}

// מחזיר את היומנים לנתוני ההתחלה ומעדכן את התצוגה.
async function resetCalendars() {
  try {
    const res = await fetch('/api/reset', { method: 'POST' });
    const payload = await res.json();
    allData = payload.data || payload;
    if (payload.weather) weatherData = payload.weather;
    renderCalendars();
    document.getElementById('approvalBox').style.display = 'none';
    document.getElementById('finalSummaryCard').style.display = 'none';
    document.getElementById('stepsContainer').innerHTML = '<p style="color:#16a34a; font-weight:600;">✔️ היומנים אופסו בהצלחה למצב ההתחלתי הנקי.</p>';
  } catch (err) {
    alert('שגיאה באיפוס היומנים: ' + err);
  }
}

// בונה טבלה לפי היומן של המשתמש שנבחר והתחזית לכל יום.
function renderCalendars() {
  if (!allData.users) return;
  const selectedUser = document.getElementById('viewCalendarUser').value || 'עמית';
  const userCal = (allData.users[selectedUser] && allData.users[selectedUser].calendar) ? allData.users[selectedUser].calendar : {};
  const days = ['Sunday', 'Monday', 'Tuesday'];
  const dayHebNames = {'Sunday': 'ראשון (Sunday)', 'Monday': 'שני (Monday)', 'Tuesday': 'שלישי (Tuesday)'};
  const hours = ['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00'];

  let headerCells = '<th>שעה</th>';
  for (const d of days) {
    const w = weatherData[d] || {};
    const wText = w.condition ? (escapeHtml(w.icon || '') + ' ' + escapeHtml(w.condition) + ' (' + escapeHtml(w.temp || '') + ')') : '';
    headerCells += '<th>' + escapeHtml(dayHebNames[d]) + '<br><small>' + wText + '</small></th>';
  }

  let rowsHtml = '';
  for (const h of hours) {
    rowsHtml += '<tr><td><strong>' + escapeHtml(h) + '</strong></td>';
    for (const d of days) {
      const val = (userCal[d] && userCal[d][h]) ? userCal[d][h] : '';
      let cls = val === 'פנוי' ? 'free-slot' : (val.includes('משתתפים:') ? 'new-meeting' : 'busy-slot');
      rowsHtml += '<td class="' + cls + '">' + escapeHtml(val) + '</td>';
    }
    rowsHtml += '</tr>';
  }
  document.getElementById('calendarTableContainer').innerHTML =
    '<table><thead><tr>' + headerCells + '</tr></thead><tbody>' + rowsHtml + '</tbody></table>';
}

// מציג את צעדי האג'נט, התשובה הסופית ואם נדרש אישור לפגישה.
function renderSteps(data) {
  if (data.mode_info) {
    updateModeBadge(data.mode_info);
  }
  const container = document.getElementById('stepsContainer');
  const summaryCard = document.getElementById('finalSummaryCard');

  if (data.final_answer) {
    summaryCard.innerText = data.final_answer;
    summaryCard.style.display = 'block';
  } else {
    summaryCard.style.display = 'none';
  }

  const stepParts = [];
  (data.steps || []).forEach(s => {
    let cls = 'step-box';
    if (s.type === 'finish') cls += ' finish';
    if (s.type === 'approval_needed') cls += ' approval';

    let detailsHtml = '';
    if (s.type === 'finish') {
      detailsHtml = '<div style="margin-top:8px; white-space:pre-wrap; font-weight:500;">' + escapeHtml(s.details) + '</div>';
    } else {
      detailsHtml = '<span class="code-line">פרמטרים: ' + escapeHtml(JSON.stringify(s.args)) + '</span>' +
                    '<span class="code-line">תוצאה: ' + escapeHtml(s.result) + '</span>';
    }
    stepParts.push('<div class="' + cls + '"><strong>' + escapeHtml(s.title) + '</strong>' + detailsHtml + '</div>');
  });
  container.innerHTML = stepParts.join('');

  const approvalBox = document.getElementById('approvalBox');
  if (data.status === 'waiting_approval' && data.pending_meeting) {
    const m = data.pending_meeting;
    document.getElementById('approvalText').innerText =
      '📅 הצעת האג\'נט: "' + m.title + '" | יום: ' + m.day + ' | שעה: ' + m.hour + ' | משתתפים: ' + (m.participants || []).join(', ');
    document.getElementById('approvalNote').innerText = data.proposal_note ? ('💡 נימוק האג\'נט: ' + data.proposal_note) : '';
    approvalBox.style.display = 'block';
    approvalBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } else {
    approvalBox.style.display = 'none';
  }
}

// שולח את המטרה לשרת ומציג את תוצאת הריצה.
async function startAgent() {
  const user = document.getElementById('userSelect').value || 'עמית';
  const goal = document.getElementById('goalInput').value.trim();
  if (!goal) {
    alert('אנא בחרי תרחיש מוכן או הקלידי מטרה בתיבת הטקסט!');
    return;
  }

  document.getElementById('stepsContainer').innerHTML = '<p style="color:#2563eb; font-weight:600;">⏳ האג\'נט חושב, בודק אילוצים ויומנים...</p>';
  document.getElementById('approvalBox').style.display = 'none';
  document.getElementById('finalSummaryCard').style.display = 'none';

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user, goal })
    });
    const data = await res.json();
    if (data.error) {
      document.getElementById('stepsContainer').innerHTML = '<p style="color:red;">שגיאה: ' + escapeHtml(data.error) + '</p>';
      return;
    }
    if (data.data) {
      allData = data.data;
      if (data.weather) weatherData = data.weather;
      renderCalendars();
    } else {
      await fetchCalendars();
    }
    renderSteps(data);
  } catch (err) {
    document.getElementById('stepsContainer').innerHTML = '<p style="color:red;">שגיאה בתקשורת עם השרת המקומי: ' + escapeHtml(err) + '</p>';
  }
}

// שולח לשרת את החלטת המשתמש לגבי המועד שהוצע.
async function sendApproval(approved) {
  const reason = document.getElementById('rejectReason').value.trim();
  document.getElementById('approvalBox').style.display = 'none';
  const loadingMsg = document.createElement('p');
  loadingMsg.style.cssText = 'color:#2563eb; font-weight:600;';
  loadingMsg.innerText = '⏳ מעבד את בחירתך ומעדכן את היומן...';
  document.getElementById('stepsContainer').appendChild(loadingMsg);

  try {
    const res = await fetch('/api/approve', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ approved, reason })
    });
    const data = await res.json();
    document.getElementById('rejectReason').value = '';
    if (data.data) {
      allData = data.data;
      if (data.weather) weatherData = data.weather;
      renderCalendars();
    } else {
      await fetchCalendars();
    }
    renderSteps(data);
  } catch (err) {
    alert('שגיאה בשליחת האישור: ' + err);
  }
}

window.onload = fetchCalendars;
</script>
</body>
</html>
"""


class AgentRequestHandler(BaseHTTPRequestHandler):
    # מבטל את הודעות הלוג האוטומטיות של שרת ה-HTTP.
    def log_message(self, format, *args):
        pass

    # שולח תשובת JSON לדפדפן.
    def _send_json(self, obj: dict, status_code: int = 200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    # מטפל בבקשות GET: הצגת הדף או שליחת נתוני היומנים.
    def do_GET(self):
        try:
            if self.path.startswith("/api/data"):
                self._send_json(
                    {
                        "data": load_data(),
                        "weather": WEATHER_DATA,
                        "mode_info": AGENT.get_connection_status(),
                    }
                )
            elif self.path == "/" or self.path.startswith("/?"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode("utf-8"))
            else:
                self._send_json({"error": f"נתיב לא נמצא: {self.path}"}, status_code=404)
        except Exception as e:
            self._send_json({"error": f"שגיאת שרת פנימית: {str(e)}"}, status_code=500)

    # מטפל בבקשות שמפעילות את האג'נט, מאשרות פגישה או מאפסות את היומנים.
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                body = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                self._send_json({"error": "קלט JSON לא תקין בבקשה."}, status_code=400)
                return

            if self.path == "/api/run":
                user = body.get("user", "עמית")
                goal = body.get("goal", "")
                result = AGENT.start(current_user=user, user_goal=goal)
                result["data"] = load_data()
                result["weather"] = WEATHER_DATA
                self._send_json(result)

            elif self.path == "/api/approve":
                approved = bool(body.get("approved", False))
                reason = str(body.get("reason", ""))
                result = AGENT.handle_approval(approved=approved, reason=reason)
                result["data"] = load_data()
                result["weather"] = WEATHER_DATA
                self._send_json(result)

            elif self.path == "/api/reset":
                clean_data = reset_data()
                self._send_json(
                    {
                        "status": "reset",
                        "data": clean_data,
                        "weather": WEATHER_DATA,
                        "mode_info": AGENT.get_connection_status(),
                    }
                )
            else:
                self._send_json({"error": f"נתיב POST לא מוכר: {self.path}"}, status_code=404)
        except Exception as e:
            self._send_json(
                {
                    "status": "error",
                    "error": f"שגיאת שרת בעיבוד הבקשה: {str(e)}",
                    "steps": AGENT.steps_log,
                },
                status_code=500,
            )


if __name__ == "__main__":
    # מפעיל את השרת המקומי ופותח את המערכת בדפדפן.
    url = f"http://127.0.0.1:{PORT}"
    print(f"Server is running! Opening browser at: {url}")
    webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", PORT), AgentRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
