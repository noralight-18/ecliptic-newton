import streamlit as st
import json
import os
import datetime
import pytz
import requests
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI

# --- 1. CONFIGURATION ---
DATA_FILE = "data.json"
USER_TIMEZONE = 'Asia/Shanghai' 
BEIJING_TZ = pytz.timezone(USER_TIMEZONE)

def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    if api_key:
        return OpenAI(api_key=api_key)
    return None

# --- 2. DATABASE HELPERS ---
def load_data():
    if not os.path.exists(DATA_FILE): 
        return {"Modules": {}, "Meta": {"last_briefing": ""}}
    with open(DATA_FILE, "r") as f:
        try: return json.load(f)
        except: return {"Modules": {}, "Meta": {"last_briefing": ""}}

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

def get_beijing_time_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%H:%M")

def get_current_date_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

def get_current_context():
    h = datetime.datetime.now(BEIJING_TZ).hour
    if 9 <= h < 18: return "In Office / Class"
    return "Personal Time"

def get_all_classes():
    return [
        "General",
        "Business Law",
        "Doing Business in China",
        "Corporate Finance",
        "International Investment",
        "Chinese 101",
        "Innovation and Entrepreneurship",
        "Strategic Management"
    ]

def get_current_module():
    return "General"

# --- 3. GOOGLE CALENDAR ENGINE (Read & Write) ---

def get_calendar_service():
    """Authenticates and returns the Google Calendar Service"""
    if "google" in st.secrets:
        creds_dict = dict(st.secrets["google"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/calendar']
        )
        return build('calendar', 'v3', credentials=creds), creds_dict.get("calendar_email", "primary")
    return None, None

def add_google_calendar_event(summary, start_iso, duration_minutes=60, reminder_minutes=15):
    """Adds event with Smart Buffer"""
    try:
        service, target_id = get_calendar_service()
        if not service: return False
        
        start_dt = datetime.datetime.fromisoformat(start_iso)
        end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
        
        overrides = []
        if reminder_minutes > 0:
            overrides.append({'method': 'popup', 'minutes': reminder_minutes})
        
        event = {
            'summary': f"{summary}", 
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': USER_TIMEZONE},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': USER_TIMEZONE},
            'reminders': {'useDefault': False, 'overrides': overrides},
        }
        
        service.events().insert(calendarId=target_id, body=event).execute()
        return True
    except Exception as e:
        print(f"❌ Calendar Write Error: {e}")
        return False

def check_calendar_availability(date_str):
    """
    Reads the calendar for a specific day and returns a list of events.
    date_str format: "YYYY-MM-DD"
    """
    try:
        service, target_id = get_calendar_service()
        if not service: return "⚠️ Calendar not connected."

        # Define start and end of that day in user timezone
        tz = pytz.timezone(USER_TIMEZONE)
        dt_start = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        dt_end = dt_start + datetime.timedelta(days=1)
        
        # Convert to ISO format with Timezone info
        iso_start = tz.localize(dt_start).isoformat()
        iso_end = tz.localize(dt_end).isoformat()

        events_result = service.events().list(
            calendarId=target_id, 
            timeMin=iso_start, 
            timeMax=iso_end, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return "No events found. You are free."
            
        summary_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            # Extract just the time part (HH:MM)
            time_str = start[11:16] if 'T' in start else "All Day"
            summary_list.append(f"- {time_str}: {event['summary']}")
            
        return "\n".join(summary_list)

    except Exception as e:
        return f"Error checking calendar: {str(e)}"

# --- 4. NOTIFICATION & AUDIT ---

def send_telegram_alert(message):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
    except Exception as e: print(f"Telegram Failed: {e}")

def check_and_send_briefing():
    data = load_data()
    today_str = get_current_date_str()
    last_sent = data.get("Meta", {}).get("last_briefing", "")
    
    if last_sent != today_str:
        todays_tasks = []
        todays_events = []
        overdue_tasks = []
        
        for mod, content in data.get("Modules", {}).items():
            for t in content.get("tasks", []):
                if t.get("date") == today_str: todays_tasks.append(f"• {t['title']}")
                elif t.get("date") < today_str: overdue_tasks.append(f"• {t['title']}")
            for e in content.get("events", []):
                if e.get("date") == today_str: todays_events.append(f"• {e.get('time','?')}: {e['title']}")
        
        if todays_tasks or todays_events or overdue_tasks:
            msg = f"☕ **Morning Briefing**\n\n"
            if todays_events: msg += f"📅 **Schedule:**\n" + "\n".join(todays_events) + "\n\n"
            else: msg += "📅 Schedule is clear.\n\n"
            if todays_tasks: msg += f"✅ **To-Do:**\n" + "\n".join(todays_tasks) + "\n\n"
            if overdue_tasks: msg += f"\n🛑 **Outstanding:**\n" + "\n".join(overdue_tasks)
            
            send_telegram_alert(msg)
            
        if "Meta" not in data: data["Meta"] = {}
        data["Meta"]["last_briefing"] = today_str
        save_data(data)

# --- 5. BRAIN: VISION, VOICE, & ROUTER ---

def transcribe_audio(audio_file, for_coach=False):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing"
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def analyze_image(image_file, manual_module="General"):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing"

    try:
        base64_image = base64.b64encode(image_file.getvalue()).decode('utf-8')
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Transcribe this document VERBATIM. Format cleanly with bullets. No summarizing."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ],
            }],
            max_tokens=1500
        )
        analysis = response.choices[0].message.content
        
        data = load_data()
        if manual_module not in data["Modules"]: data["Modules"][manual_module] = {"tasks":[], "events":[], "knowledge":[]}
        if "knowledge" not in data["Modules"][manual_module]: data["Modules"][manual_module]["knowledge"] = []
        
        item = {
            "id": len(data["Modules"][manual_module]["knowledge"]) + 1,
            "title": "📷 Document Scan",
            "details": analysis,
            "date": get_current_date_str(),
            "created_at": get_beijing_time_str()
        }
        data["Modules"][manual_module]["knowledge"].append(item)
        save_data(data)
        return analysis
    except Exception as e: return f"Error: {str(e)}"

def process_assistant_input(user_text, manual_module="General"):
    client = get_openai_client()
    if not client: return {"error": "API Key Missing"}
    data = load_data()
    
    system_prompt = f"""
    You are Andy (Emily). Current Time: {datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")}
    
    JOB: Route information.
    
    1. INTENT:
       - ACTIONABLE (Meeting, Call, Deadline) -> TASK or EVENT.
       - INFORMATIONAL (Notes) -> NOTE.
    
    2. SMART REMINDERS:
       - TRAVEL/PHYSICAL -> 60 mins.
       - VIRTUAL -> 15 mins.
       - CALL -> 2 mins.
       - EXAM -> 120 mins.
       
    3. EXPLICIT TELEGRAM -> notify_telegram = TRUE.

    OUTPUT JSON:
    {{
        "type": "task" | "event" | "note",
        "module": "Subject or 'General'",
        "title": "Title",
        "details": "Details",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "reminder_minutes": INTEGER,
        "notify_telegram": boolean
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Context: {manual_module}. Input: {user_text}"}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e: return {"error": str(e)}

    # Force Reminders to Calendar
    if "remind" in user_text.lower() and result.get("type") == "task":
        result["type"] = "event"

    # Save
    item_type = result.get("type")
    db_key = "events" if item_type == "event" else "knowledge" if item_type == "note" else "tasks"
    target_mod = result.get("module", manual_module)
    
    if target_mod not in data["Modules"]: data["Modules"][target_mod] = {"tasks": [], "events": [], "knowledge": []}
    if db_key not in data["Modules"][target_mod]: data["Modules"][target_mod][db_key] = []

    item = {
        "id": len(data["Modules"][target_mod][db_key]) + 1,
        "title": result.get("title"),
        "details": result.get("details"),
        "date": result.get("date", get_current_date_str()),
        "created_at": get_beijing_time_str()
    }
    if item_type == "event": item["time"] = result.get("time", "09:00")
        
    data["Modules"][target_mod][db_key].append(item)
    save_data(data)
    
    # Actions
    if item_type == "event":
        iso = f"{result.get('date')}T{result.get('time','09:00')}:00"
        buffer = result.get("reminder_minutes", 10)
        success = add_google_calendar_event(result.get('title'), iso, reminder_minutes=buffer)
        result["calendar_status"] = success
        result["buffer"] = buffer

    if result.get("notify_telegram") == True:
        send_telegram_alert(f"📱 **Instant Alert:**\n{result.get('title')}")
        result["telegram_sent"] = True
        
    return result

def chat_with_emily(user_message, history):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing."

    # 1. CHECK INTENT (Router)
    router_prompt = f"""
    Analyze user input. 
    Current Date: {get_current_date_str()}.
    
    Does the user want to:
    A. PERFORM an action (create task, schedule event, save note).
    B. QUERY the calendar (ask "what do I have on Friday?", "am I free?").
    C. CHAT (general conversation).
    
    Output one word: ACTION, QUERY, or CHAT.
    """
    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":router_prompt}, {"role":"user","content":user_message}]
    )
    intent = check.choices[0].message.content.upper()

    # 2. HANDLE INTENTS
    
    # --- QUERY CALENDAR (READ) ---
    if "QUERY" in intent:
        # Ask GPT to extract the date
        date_extract = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role":"system","content":f"Extract the target date from the user's question. Current Date: {get_current_date_str()}. Output ONLY YYYY-MM-DD."},
                {"role":"user","content":user_message}
            ]
        )
        target_date = date_extract.choices[0].message.content.strip()
        
        # Check API
        calendar_data = check_calendar_availability(target_date)
        
        # Synthesize Answer
        final_answer = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role":"system","content":"You are Andy. Report the schedule to the user based on the data provided."},
                {"role":"user","content":f"User Question: {user_message}\nCalendar Data: {calendar_data}"}
            ]
        )
        return final_answer.choices[0].message.content

    # --- ACTION (WRITE) ---
    elif "ACTION" in intent:
        res = process_assistant_input(user_message)
        if "error" in res: return f"❌ Error: {res['error']}"
        
        msg = "✅ **Handled.**"
        if res.get("type") == "event":
            buffer = res.get("buffer", 10)
            msg += f" Scheduled **{res.get('title')}**."
            msg += f" (Alert {buffer} mins prior)."
        elif res.get("type") == "note":
             msg += f" Saved note to **{res.get('module')}**."
        else:
            msg += f" Added task **{res.get('title')}**."
            
        if res.get("telegram_sent"): msg += " 📲 Sent to phone."
        return msg
        
    # --- CHAT ---
    else:
        msgs = [{"role":"system","content":"You are Andy Sachs. Professional, efficient."}] + history + [{"role":"user","content":user_message}]
        return client.chat.completions.create(model="gpt-4o", messages=msgs).choices[0].message.content

# --- 6. UI HELPERS ---
def delete_item(mod, type_, id_):
    data = load_data()
    if mod in data["Modules"] and type_ in data["Modules"][mod]:
        data["Modules"][mod][type_] = [i for i in data["Modules"][mod][type_] if i.get("id") != id_]
        save_data(data)

def add_manual_item(mod, type_, title, details, date):
    data = load_data()
    if mod not in data["Modules"]: data["Modules"][mod] = {"tasks": [], "events": [], "knowledge": []}
    if type_ not in data["Modules"][mod]: data["Modules"][mod][type_] = []
    new_id = len(data["Modules"][mod][type_]) + 1
    item = {"id": new_id, "title": title, "details": details, "date": date}
    data["Modules"][mod][type_].append(item)
    save_data(data)

def analyze_speech_coach(transcript):
    client = get_openai_client()
    if not client: return {"grade": "N/A", "critique": "API Key Missing"}
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": f"Analyze speech. Grade (A-F), score pacing (1-10), count fillers. JSON. Text: {transcript}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"grade": "N/A", "pacing_score": 0, "filler_count": 0, "critique": "Error analyzing."}
