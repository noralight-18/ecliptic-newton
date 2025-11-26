import streamlit as st
import json
import os
import datetime
import pytz
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI

# --- CONFIGURATION & SETUP ---
DATA_FILE = "data.json"
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# Initialize OpenAI
def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    return OpenAI(api_key=api_key) if api_key else None

# --- DATABASE MANAGEMENT ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"Modules": {}}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"Modules": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_current_date_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

def get_beijing_time_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%H:%M")

def get_current_context():
    hour = datetime.datetime.now(BEIJING_TZ).hour
    if 9 <= hour < 12: return "In Class: Strategy"
    if 12 <= hour < 14: return "Lunch Break"
    return "Free Time / Study"

def get_current_module():
    return "General"

def get_all_classes():
    return ["Business Law", "Strategic Management", "Marketing", "Finance"]

# --- AUTOMATION: NOTIFICATIONS ---

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
    except Exception as e:
        print(f"Calendar Failed: {e}")
        return False

# --- THE BRAIN: INTELLIGENT CAPTURE ---

def transcribe_audio(audio_file, for_coach=False):
    client = get_openai_client()
    if not client: return "No API Key"
    
    transcript = client.audio.transcriptions.create(
        model="whisper-1", 
        file=audio_file,
        response_format="text"
    )
    return transcript

def process_assistant_input(user_text, manual_module="General", last_task_metadata=None):
    client = get_openai_client()
    data = load_data()
    
    current_time = datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    
    system_prompt = f"""
    You are Emily, an Executive OS.
    Current Time: {current_time}
    
    DECISION LOGIC:
    1. EVENT (Google Calendar): Meeting people, classes, specific time.
    2. TASK (Telegram): Individual work, assignments, deadlines.
    3. NOTE: Info to remember.

    OUTPUT JSON ONLY:
    {{
        "type": "task" | "event" | "note",
        "module": "Subject or 'General'",
        "title": "Short summary",
        "details": "Full details",
        "date": "YYYY-MM-DD",
        "time": "HH:MM" (24h, Default 09:00),
        "duration_mins": 60
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
    
    # --- FIX IS HERE: Correctly map the types to database keys ---
    type_map = {
        "task": "tasks",
        "event": "events",
        "note": "knowledge"  # This was the missing link causing the crash
    }
    
    # Get the correct DB folder name (default to 'knowledge' if unknown)
    db_key = type_map.get(result.get("type"), "knowledge")
    
    target_mod = result.get("module", manual_module)
    if target_mod not in data["Modules"]:
        data["Modules"][target_mod] = {"tasks": [], "events": [], "knowledge": []}
    
    # Use the MAPPED key to calculate ID
    new_id = len(data["Modules"][target_mod][db_key]) + 1
    
    item_record = {
        "id": new_id,
        "title": result.get("title", "Untitled"),
        "details": result.get("details", ""),
        "date": result.get("date", get_current_date_str()),
        "created_at": current_time
    }
    
    if result.get("type") == "event":
        item_record["time"] = result.get("time", "09:00")
    
    # Save to the correct list
    data["Modules"][target_mod][db_key].append(item_record)
    save_data(data)
    
    # --- AUTOMATION TRIGGERS ---
    if result.get("type") == "task":
        msg = f"⚡ *Emily Task*\n\n📌 **{result['title']}**\n📅 Due: {result['date']}\n📂 {target_mod}"
        send_telegram_alert(msg)
        
    elif result.get("type") == "event":
        iso_start = f"{result['date']}T{result.get('time', '09:00')}:00"
        add_google_calendar_event(result["title"], iso_start, result.get("duration_mins", 60))
        
    return result

# --- OMNISCIENT CHAT ---

def chat_with_emily(user_message, history):
    client = get_openai_client()
    
    # Check if command
    check_prompt = "Is this user asking to create a task, schedule an event, or save a note? Answer YES or NO."
    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": check_prompt}, {"role": "user", "content": user_message}]
    )
    
    if "YES" in check.choices[0].message.content:
        res = process_assistant_input(user_message)
        if "error" in res:
            return "I tried to process that but encountered an error."
            
        if res["type"] == "task":
            return f"✅ Done. Added task **{res['title']}** and notified your phone."
        elif res["type"] == "event":
            return f"✅ Done. Scheduled **{res['title']}** on Google Calendar."
        else:
            return f"✅ Saved note: {res['title']}"
            
    system_persona = "You are Emily, a witty Executive OS. Keep answers concise."
    messages = [{"role": "system", "content": system_persona}] + history + [{"role": "user", "content": user_message}]
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    return response.choices[0].message.content

# --- VISION & COACH ---
def analyze_image(image_file, manual_module="General"):
    return "Image analysis placeholder."

def analyze_speech_coach(transcript):
    client = get_openai_client()
    prompt = f"Analyze speech. Grade (A-F), score pacing (1-10), count fillers. JSON. Text: {transcript}"
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"grade": "N/A", "pacing_score": 0, "filler_count": 0, "critique": "Error analyzing."}

def delete_item(mod, type_, id_):
    data = load_data()
    if mod in data["Modules"] and type_ in data["Modules"][mod]:
        data["Modules"][mod][type_] = [i for i in data["Modules"][mod][type_] if i.get("id") != id_]
        save_data(data)

def add_manual_item(mod, type_, title, details, date):
    data = load_data()
    if mod not in data["Modules"]:
        data["Modules"][mod] = {"tasks": [], "events": [], "knowledge": []}
    
    # Ensure list exists
    if type_ not in data["Modules"][mod]:
        data["Modules"][mod][type_] = []
        
    new_id = len(data["Modules"][mod][type_]) + 1
    item = {"id": new_id, "title": title, "details": details, "date": date}
    data["Modules"][mod][type_].append(item)
    save_data(data)
