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
    # Try multiple ways to find the key to prevent crashes
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    
    if api_key:
        return OpenAI(api_key=api_key)
    return None

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

def get_current_date_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

# --- INTELLIGENT NOTIFICATIONS ---

def send_telegram_alert(message, delay_minutes=0):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            
            payload = {
                "chat_id": chat_id, 
                "text": message, 
                "parse_mode": "Markdown"
            }
            
            # DELAY LOGIC
            if delay_minutes > 0:
                future_time = int(time.time() + (delay_minutes * 60))
                payload["schedule_date"] = future_time
            
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
    if not client: return "⚠️ API Key Missing"
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def process_assistant_input(user_text, manual_module="General", last_task_metadata=None):
    client = get_openai_client()
    if not client: return {"error": "API Key Missing"}

    data = load_data()
    
    # SYSTEM PROMPT: Calculates Delays & Categories
    current_time_str = datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    
    system_prompt = f"""
    You are Emily, an intelligent Executive OS.
    Current System Time (Beijing): {current_time_str}
    
    YOUR GOAL: Classify the user's input and extract structured data.

    CATEGORIES:
    1. REMINDER (Telegram): User wants an alert at a specific time (e.g., "Remind me in 20 mins", "Alert me at 10pm").
    2. EVENT (Calendar): User has a meeting, class, or fixed schedule.
    3. TASK (To-Do): Homework, buying items, general to-dos.
    4. NOTE: General info to save.

    OUTPUT JSON ONLY:
    {{
        "type": "task" | "event" | "note" | "reminder",
        "module": "Subject (Business Law, Strategy) or 'General'",
        "title": "Short, clear title",
        "details": "Full context",
        "date": "YYYY-MM-DD",
        "time": "HH:MM" (24h format),
        "delay_minutes": 0 (INTEGER. Calculate this! If it's 9:00 and user says 9:30, delay is 30. If user says 'in 1 hour', delay is 60.)
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
    except Exception as e:
        return {"error": str(e)}

    # Map to DB Keys
    type_map = {"task": "tasks", "event": "events", "note": "knowledge", "reminder": "tasks"}
    db_key = type_map.get(result.get("type"), "knowledge")
    target_mod = result.get("module", manual_module)
    
    # Safety: Create module/list if missing
    if target_mod not in data["Modules"]:
        data["Modules"][target_mod] = {"tasks": [], "events": [], "knowledge": []}
    if db_key not in data["Modules"][target_mod]:
        data["Modules"][target_mod][db_key] = []

    # Save Item
    item = {
        "id": len(data["Modules"][target_mod][db_key]) + 1,
        "title": result.get("title", "Untitled"),
        "details": result.get("details", ""),
        "date": result.get("date", get_current_date_str()),
        "created_at": get_beijing_time_str()
    }
    data["Modules"][target_mod][db_key].append(item)
    save_data(data)
    
    # EXECUTE ACTION
    delay = result.get("delay_minutes", 0)
    
    if result.get("type") == "reminder":
        # Specific Logic for Reminders
        msg = f"⏰ *Reminder*\n\n{result.get('title')}"
        send_telegram_alert(msg, delay_minutes=delay)
        
    elif result.get("type") == "task":
        # Immediate Task Notification
        msg = f"⚡ *New Task*\n\n{result.get('title')}\nDue: {result.get('date')}"
        send_telegram_alert(msg)
        
    elif result.get("type") == "event":
        # Calendar Sync
        iso = f"{result.get('date')}T{result.get('time','09:00')}:00"
        add_google_calendar_event(result.get('title'), iso)
        
    return result

def chat_with_emily(user_message, history):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing."

    # 1. ROUTER: Decide if this is a command
    # Improved Prompt: Explicitly mentions "reminder" and asks for simple yes/no
    check_prompt = """
    Analyze the user input. Is the user asking to:
    - Create a task?
    - Schedule an event?
    - Set a reminder?
    - Save a note?
    
    Answer with one word: YES or NO.
    """
    
    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":check_prompt}, {"role":"user","content":user_message}]
    )
    
    # 2. LOGIC: Case-insensitive check (The fix!)
    decision = check.choices[0].message.content.strip().upper()
    
    if "YES" in decision:
        res = process_assistant_input(user_message)
        if "error" in res:
            return f"❌ Error: {res['error']}"
            
        if res.get("delay_minutes", 0) > 0:
            return f"✅ Done. I've set a reminder for **{res['delay_minutes']} minutes** from now on your phone."
        elif res.get("type") == "event":
            return f"✅ Done. Scheduled **{res.get('title')}** on Google Calendar."
        else:
            return f"✅ Done. Added **{res.get('title')}** to your system."
        
    # 3. FALLBACK: Normal Chat
    # We explicitly tell her she has tools so she doesn't deny her abilities.
    system_persona = """
    You are Emily, a proactive Executive OS.
    You have access to the user's Google Calendar and Telegram for reminders.
    If the user asks for a reminder and you ended up here, apologize and say you might have missed the trigger, but you CAN do it if they phrase it clearly.
    Keep answers concise and professional.
    """
    msgs = [{"role":"system","content":system_persona}] + history + [{"role":"user","content":user_message}]
    return client.chat.completions.create(model="gpt-4o", messages=msgs).choices[0].message.content

# Mocks
def analyze_image(f, m="General"): return "Image Analysis Placeholder"
def analyze_speech_coach(t): return {"grade": "B", "pacing_score": 7, "filler_count": 0, "critique": "Good."}
def delete_item(m, t, i): pass
def add_manual_item(m, t, ti, d, da): pass
def get_all_classes(): return ["Business Law", "Strategy"]
def get_current_module(): return "General"
def get_current_context(): return "Working"
