import streamlit as st
import json
import os
import datetime
import time
import pytz
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI

# --- CONFIGURATION ---
DATA_FILE = "data.json"
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    return OpenAI(api_key=api_key) if api_key else None

# --- DATABASE HELPERS ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"Modules": {}}
    with open(DATA_FILE, "r") as f:
        try: return json.load(f)
        except: return {"Modules": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

def get_beijing_time_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%H:%M")

def get_current_context():
    h = datetime.datetime.now(BEIJING_TZ).hour
    return "In Class" if 9 <= h < 12 else "Free Time"

def get_all_classes():
    return ["Business Law", "Strategic Management", "Marketing", "Finance"]

def get_current_module():
    return "General"

def get_current_date_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

# --- INTELLIGENT NOTIFICATIONS ---

def send_telegram_alert(message, delay_minutes=0):
    """
    Sends a message. If delay_minutes > 0, it schedules it on Telegram server.
    """
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            
            payload = {
                "chat_id": chat_id, 
                "text": message, 
                "parse_mode": "Markdown"
            }
            
            # LOGIC FOR DELAY
            if delay_minutes > 0:
                # Calculate future Unix timestamp
                future_time = int(time.time() + (delay_minutes * 60))
                payload["schedule_date"] = future_time
                print(f"Scheduling message for timestamp: {future_time}")

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Failed: {e}")

def add_google_calendar_event(summary, start_iso, duration_minutes=60):
    try:
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=creds)
            
            start_dt = datetime.datetime.fromisoformat(start_iso)
            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
            
            event = {
                'summary': f"🎓 {summary}", 
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Shanghai'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Shanghai'},
            }
            service.events().insert(calendarId='primary', body=event).execute()
            return True
    except: return False

# --- THE BRAIN ---

def transcribe_audio(audio_file, for_coach=False):
    client = get_openai_client()
    if not client: return "No API"
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def process_assistant_input(user_text, manual_module="General", last_task_metadata=None):
    client = get_openai_client()
    data = load_data()
    
    system_prompt = f"""
    You are Emily. Current Time: {datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")}
    
    DECISION LOGIC:
    1. REMINDER (Telegram): If user says "Remind me in 5 mins" or "Alert me in 1 hour".
    2. EVENT (Calendar): Specific meeting time/class.
    3. TASK (To-Do): Homework/Deadline.
    4. NOTE: Info.

    OUTPUT JSON ONLY:
    {{
        "type": "task" | "event" | "note" | "reminder",
        "module": "Subject or 'General'",
        "title": "Summary",
        "details": "Details",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "delay_minutes": 0 (Integer. ONLY if user asked for a delay like 'in 5 mins'. Default 0)
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
    except: return {"error": "GPT Error"}

    # DB Mapping
    type_map = {"task": "tasks", "event": "events", "note": "knowledge", "reminder": "tasks"}
    db_key = type_map.get(result.get("type"), "knowledge")
    target_mod = result.get("module", manual_module)
    
    if target_mod not in data["Modules"]:
        data["Modules"][target_mod] = {"tasks": [], "events": [], "knowledge": []}
        
    # Save to DB
    item = {
        "id": len(data["Modules"][target_mod][db_key]) + 1,
        "title": result.get("title"),
        "details": result.get("details"),
        "date": result.get("date", get_current_date_str()),
        "created_at": get_beijing_time_str()
    }
    data["Modules"][target_mod][db_key].append(item)
    save_data(data)
    
    # TRIGGERS
    delay = result.get("delay_minutes", 0)
    
    if result["type"] == "reminder" or (result["type"] == "task" and delay > 0):
        msg = f"⏰ *Reminder from Emily*\n\n{result['title']}"
        send_telegram_alert(msg, delay_minutes=delay)
        
    elif result["type"] == "task":
        send_telegram_alert(f"⚡ *New Task*\n{result['title']}\nDue: {result['date']}")
        
    elif result["type"] == "event":
        iso = f"{result['date']}T{result.get('time','09:00')}:00"
        add_google_calendar_event(result['title'], iso)
        
    return result

def chat_with_emily(user_message, history):
    # Same simplified logic as before, leveraging process_assistant_input
    client = get_openai_client()
    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":"Does user want to create a task/event/reminder? YES/NO"}, {"role":"user","content":user_message}]
    )
    if "YES" in check.choices[0].message.content:
        res = process_assistant_input(user_message)
        if res.get("delay_minutes", 0) > 0:
            return f"✅ Done. I've set a reminder for **{res['delay_minutes']} minutes** from now."
        return f"✅ Done. Saved **{res['title']}**."
        
    # Normal Chat
    msgs = [{"role":"system","content":"You are Emily, a witty Executive OS."}] + history + [{"role":"user","content":user_message}]
    return client.chat.completions.create(model="gpt-4o", messages=msgs).choices[0].message.content

# Placeholder Mocks
def analyze_image(f, m="General"): return "Image Analysis Placeholder"
def analyze_speech_coach(t): return {"grade": "B", "pacing_score": 7, "filler_count": 3, "critique": "Good flow."}
def delete_item(m, t, i): pass 
def add_manual_item(m, t, ti, d, da): pass
