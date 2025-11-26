import streamlit as st
import json
import os
import datetime
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

def send_telegram_alert(message):
    """Sends an IMMEDIATE message to Telegram."""
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Failed: {e}")

def add_google_calendar_event(summary, start_iso, duration_minutes=30):
    """Adds event to Google Calendar (This works as the Reminder)"""
    try:
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=creds)
            
            # Create Time Objects
            start_dt = datetime.datetime.fromisoformat(start_iso)
            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
            
            event = {
                'summary': f"⏰ {summary}",  # Add Alarm Clock Emoji
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Shanghai'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Shanghai'},
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 0}, # Notify at exact time
                    ],
                },
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
    current_time_str = datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    
    # SYSTEM PROMPT: Simpler Logic
    system_prompt = f"""
    You are Emily, an intelligent Executive OS.
    Current System Time (Beijing): {current_time_str}
    
    YOUR GOAL: Classify input.
    
    CRITICAL RULE: 
    - If the user specifies a TIME (e.g. "at 10pm", "in 1 hour"), it MUST be an EVENT/REMINDER (Calendar).
    - If the user specifies NO TIME (e.g. "Buy milk"), it is a TASK (Telegram).

    OUTPUT JSON ONLY:
    {{
        "type": "task" | "event" | "note",
        "module": "Subject or 'General'",
        "title": "Short title",
        "details": "Full context",
        "date": "YYYY-MM-DD",
        "time": "HH:MM" (24h format. If user says '10pm', output '22:00'. If user says 'in 1 hour' and now is 14:00, output '15:00'.)
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

    # Logic: Reminders are now treated as Events so they go to Calendar
    item_type = result.get("type")
    
    # Save to Database
    db_key = "events" if item_type == "event" else "tasks" if item_type == "task" else "knowledge"
    target_mod = result.get("module", manual_module)
    
    if target_mod not in data["Modules"]: data["Modules"][target_mod] = {"tasks": [], "events": [], "knowledge": []}
    if db_key not in data["Modules"][target_mod]: data["Modules"][target_mod][db_key] = []

    item = {
        "id": len(data["Modules"][target_mod][db_key]) + 1,
        "title": result.get("title", "Untitled"),
        "details": result.get("details", ""),
        "date": result.get("date", get_current_date_str()),
        "created_at": get_beijing_time_str()
    }
    if item_type == "event":
        item["time"] = result.get("time", "09:00")
        
    data["Modules"][target_mod][db_key].append(item)
    save_data(data)
    
    # --- ROUTING LOGIC ---
    
    # 1. TIME-BASED (Calendar)
    if item_type == "event":
        iso = f"{result.get('date')}T{result.get('time','09:00')}:00"
        success = add_google_calendar_event(result.get('title'), iso)
        if success:
            # We send a Telegram just to confirm we did it, but the REMINDER is in the Calendar
            send_telegram_alert(f"🗓️ *Scheduled*\n\nI've added **{result.get('title')}** to your Calendar for {result.get('time')}.")
            
    # 2. IMMEDIATE (Telegram)
    elif item_type == "task":
        send_telegram_alert(f"⚡ *New Task*\n\n{result.get('title')}\nDue: {result.get('date')}")
        
    return result

def chat_with_emily(user_message, history):
    client = get_openai_client()
    if not client: return "⚠️ API Key Missing."

    check_prompt = "Is user asking to create a task, event, reminder, or note? Answer YES or NO."
    check = client.chat.completions.create(
        model="gpt-4o", messages=[{"role":"system","content":check_prompt}, {"role":"user","content":user_message}]
    )
    
    if "YES" in check.choices[0].message.content.upper():
        res = process_assistant_input(user_message)
        if "error" in res: return f"❌ Error: {res['error']}"
        
        if res.get("type") == "event":
            return f"✅ Done. I've scheduled **{res.get('title')}** on your Google Calendar at {res.get('time')}."
        else:
            return f"✅ Done. Added **{res.get('title')}** to your tasks."
        
    msgs = [{"role":"system","content":"You are Emily. Concise answers."}] + history + [{"role":"user","content":user_message}]
    return client.chat.completions.create(model="gpt-4o", messages=msgs).choices[0].message.content

# Mocks
def analyze_image(f, m="General"): return "Analysis Placeholder"
def analyze_speech_coach(t): return {"grade": "B", "critique": "Good."}
def delete_item(m, t, i): pass
def add_manual_item(m, t, ti, d, da): pass
def get_all_classes(): return ["Business Law", "Strategy"]
def get_current_module(): return "General"
def get_current_context(): return "Working"
