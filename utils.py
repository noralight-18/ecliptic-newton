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
    if 9 <= h < 18: return "Working / Studying"
    return "Free Time"

def get_all_classes():
    return ["Business Law", "Strategic Management", "Marketing", "Finance"]

def get_current_module():
    return "General"

# --- 3. NOTIFICATION SYSTEMS ---

def send_telegram_alert(message):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Failed: {e}")

def add_google_calendar_event(summary, start_iso, duration_minutes=60):
    try:
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            
            # Use 'calendar_email' from secrets to target YOUR calendar
            target_id = creds_dict.get("calendar_email", "primary")
            
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=creds)
            
            start_dt = datetime.datetime.fromisoformat(start_iso)
            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
            
            event = {
                'summary': f"⏰ {summary}", 
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': USER_TIMEZONE},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': USER_TIMEZONE},
                'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 0}]},
            }
            
            service.events().insert(calendarId=target_id, body=event).execute()
            print(f"✅ Success: Added {summary} to {target_id}")
            return True
    except Exception as e:
        print(f"❌ Calendar Error: {e}")
        return False

# --- 4. MORNING BRIEFING ---
def check_and_send_briefing():
    data = load_data()
    today_str = get_current_date_str()
    last_sent = data.get("Meta", {}).get("last_briefing", "")
    
    if last_sent != today_str:
        todays_tasks = []
        todays_events = []
        
        for mod, content in data.get("Modules", {}).items():
            for t in content.get("tasks", []):
                if t.get("date") == today_str: todays_tasks.append(f"• {t['title']}")
            for e in content.get("events", []):
                if e.get("date") == today_str: todays_events.append(f"• {e.get('time','?')}: {e['title']}")
        
        if todays_tasks or todays_events:
            msg = f"🌅 **Morning Briefing** ({today_str})\n\n"
            msg += f"📅 **Events:**\n" + ("\n".join(todays_events) if todays_events else "None") + "\n\n"
            msg += f"✅ **Tasks:**\n" + ("\n".join(todays_tasks) if todays_tasks else "None")
            send_telegram_alert(msg)
            
            if "Meta" not in data: data["Meta"] = {}
            data["Meta"]["last_briefing"] = today_str
            save_data(data)

# --- 5. THE AI BRAIN (Vision + Voice + Chat) ---

def transcribe_audio(audio_file, for_coach=False):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing"
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def analyze_image(image_file, manual_module="General"):
    """
    Real Vision Implementation. Fixes the TypeError.
    """
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing"

    try:
        # Encode image to Base64
        base64_image = base64.b64encode(image_file.getvalue()).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image. If it's a document, transcribe key details. If it's a scene, describe it relevant to my work. Keep it concise."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ],
                }
            ],
            max_tokens=800
        )
        
        analysis = response.choices[0].message.content
        
        # Save to DB
        data = load_data()
        if manual_module not in data["Modules"]: data["Modules"][manual_module] = {"tasks":[], "events":[], "knowledge":[]}
        if "knowledge" not in data["Modules"][manual_module]: data["Modules"][manual_module]["knowledge"] = []
        
        item = {
            "id": len(data["Modules"][manual_module]["knowledge"]) + 1,
            "title": "📷 Scan",
            "details": analysis,
            "date": get_current_date_str(),
            "created_at": get_beijing_time_str()
        }
        data["Modules"][manual_module]["knowledge"].append(item)
        save_data(data)
        
        return analysis

    except Exception as e:
        return f"Error analyzing image: {str(e)}"

def process_assistant_input(user_text, manual_module="General", last_task_metadata=None):
    client = get_openai_client()
    if not client: return {"error": "API Key Missing"}

    data = load_data()
    
    system_prompt = f"""
    You are Emily. Current Time: {datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")}
    
    LOGIC: 
    1. SPECIFIC TIME ("at 2pm") -> EVENT (Calendar).
    2. NO TIME ("Buy milk") -> TASK (Internal List).
    3. EXPLICIT ("Send to Telegram") -> notify_telegram = TRUE.
    
    OUTPUT JSON ONLY:
    {{
        "type": "task" | "event" | "note",
        "module": "Subject or 'General'",
        "title": "Title",
        "details": "Details",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "notify_telegram": boolean
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context: {manual_module}. Input: {user_text}"}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e: return {"error": str(e)}

    # Force Reminders to Calendar
    if "remind" in user_text.lower() and result.get("type") == "task":
        result["type"] = "event"

    # Save
    item_type = result.get("type")
    db_key = "events" if item_type == "event" else "tasks" if item_type == "task" else "knowledge"
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
    
    # External Actions
    if item_type == "event":
        iso = f"{result.get('date')}T{result.get('time','09:00')}:00"
        success = add_google_calendar_event(result.get('title'), iso)
        result["calendar_status"] = success

    if result.get("notify_telegram") == True:
        send_telegram_alert(f"📱 **Sent to Phone:**\n{result.get('title')}\n{result.get('details')}")
        result["telegram_sent"] = True
        
    return result

def chat_with_emily(user_message, history):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing."

    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":"Is user asking to create a task/event? YES/NO"}, {"role":"user","content":user_message}]
    )
    
    if "YES" in check.choices[0].message.content.upper():
        res = process_assistant_input(user_message)
        if "error" in res: return f"❌ Error: {res['error']}"
        
        response_msg = "✅ **Done.**"
        if res.get("type") == "event":
            if res.get("calendar_status"): response_msg += f" Scheduled **{res.get('title')}** on Calendar."
            else: response_msg += " (⚠️ Calendar Sync Failed - Check Secrets)"
        else:
            response_msg += f" Added **{res.get('title')}**."
            
        if res.get("telegram_sent"):
            response_msg += " 📲 Sent to Telegram."
            
        return response_msg
        
    msgs = [{"role":"system","content":"You are Emily. Concise answers."}] + history + [{"role":"user","content":user_message}]
    return client.chat.completions.create(model="gpt-4o", messages=msgs).choices[0].message.content

# --- 6. UI HELPERS (Required for Buttons) ---

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
    
    # Simple Coach Logic
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": f"Analyze speech. Grade (A-F), score pacing (1-10), count fillers. JSON. Text: {transcript}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"grade": "N/A", "pacing_score": 0, "filler_count": 0, "critique": "Error analyzing."}
