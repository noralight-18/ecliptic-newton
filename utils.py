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
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_current_date_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

def get_beijing_time_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%H:%M")

def get_current_context():
    # Simple hardcoded context for now (e.g., checks time to guess class)
    hour = datetime.datetime.now(BEIJING_TZ).hour
    if 9 <= hour < 12: return "In Class: Strategy"
    if 12 <= hour < 14: return "Lunch Break"
    return "Free Time / Study"

def get_current_module():
    # Logic to guess module based on day/time could go here
    return "General"

def get_all_classes():
    # Load from a schedule.json if you have one, or return defaults
    return ["Business Law", "Strategic Management", "Marketing", "Finance"]

# --- AUTOMATION: NOTIFICATIONS ---

def send_telegram_alert(message):
    """Buzzes your phone via Telegram."""
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
    """Pushes event to Google Calendar."""
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
    """
    Decides if it's a Task or Event, Updates DB, and Sends Notification automatically.
    """
    client = get_openai_client()
    data = load_data()
    
    current_time = datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    
    # 1. THE DECISION PROMPT
    system_prompt = f"""
    You are Emily, an Executive OS for a college student.
    Current Time (Beijing): {current_time}
    
    DECISION LOGIC:
    1. EVENT (Google Calendar): If the input involves meeting people, classes, or specific time-bound attendance.
    2. TASK (Telegram): If the input is individual work, assignments, or to-dos with a deadline.
    3. NOTE: If it's just information to remember.

    OUTPUT JSON ONLY:
    {{
        "type": "task" | "event" | "note",
        "module": "Subject name (e.g. Business Law) or 'General'",
        "title": "Short summary",
        "details": "Full details",
        "date": "YYYY-MM-DD" (Target date),
        "time": "HH:MM" (Start time, 24h format. Default 09:00 if missing),
        "duration_mins": 60 (For events)
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context Module: {manual_module}. Input: {user_text}"}
        ],
        response_format={"type": "json_object"}
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # 2. SAVE TO DATABASE
    target_mod = result.get("module", manual_module)
    if target_mod not in data["Modules"]:
        data["Modules"][target_mod] = {"tasks": [], "events": [], "knowledge": []}
    
    new_id = len(data["Modules"][target_mod][result["type"] + "s"]) + 1
    item_record = {
        "id": new_id,
        "title": result["title"],
        "details": result["details"],
        "date": result["date"],
        "created_at": current_time
    }
    
    # Store in JSON
    if result["type"] == "task":
        data["Modules"][target_mod]["tasks"].append(item_record)
    elif result["type"] == "event":
        item_record["time"] = result.get("time", "09:00")
        data["Modules"][target_mod]["events"].append(item_record)
    elif result["type"] == "note":
         data["Modules"][target_mod]["knowledge"].append(item_record)
         
    save_data(data)
    
    # 3. AUTOMATION TRIGGERS (The "Less Manual" Part)
    if result["type"] == "task":
        msg = f"⚡ *Emily Task Manager*\n\n📌 **{result['title']}**\n📅 Due: {result['date']}\n📂 {target_mod}\n\n_{result['details']}_"
        send_telegram_alert(msg)
        
    elif result["type"] == "event":
        # Construct ISO time for Google
        iso_start = f"{result['date']}T{result.get('time', '09:00')}:00"
        add_google_calendar_event(result["title"], iso_start, result.get("duration_mins", 60))
        
    return result

# --- OMNISCIENT CHAT ---

def chat_with_emily(user_message, history):
    """
    Handles standard chat but also listens for commands to execute.
    """
    client = get_openai_client()
    
    # Check if this is a command (Smart routing)
    # We reuse the logic above if it looks like a command
    check_prompt = "Is this user asking to create a task, schedule an event, or save a note? Answer YES or NO."
    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": check_prompt}, {"role": "user", "content": user_message}]
    )
    
    if "YES" in check.choices[0].message.content:
        # Route to the processor
        res = process_assistant_input(user_message)
        if res["type"] == "task":
            return f"✅ Done. I've added **{res['title']}** to your tasks and sent it to your phone."
        elif res["type"] == "event":
            return f"✅ Done. I've scheduled **{res['title']}** on your Google Calendar."
        else:
            return f"✅ Saved note: {res['title']}"
            
    # Otherwise, normal chat
    system_persona = """
    You are Emily, a witty, proactive Executive OS. 
    Keep answers concise, visual, and helpful. 
    You have access to the user's context.
    """
    
    messages = [{"role": "system", "content": system_persona}] + history + [{"role": "user", "content": user_message}]
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    return response.choices[0].message.content

# --- VISION ---
def analyze_image(image_file, manual_module="General"):
    client = get_openai_client()
    # In a real app, base64 encode the image. 
    # For Streamlit simplified, we mock the vision response or use a specific library.
    # Assuming GPT-4o vision capability here:
    return "Image analysis requires base64 encoding implementation. (Feature Placeholder)"

def analyze_speech_coach(transcript):
    # Mock logic for the coach - normally uses GPT to grade text
    client = get_openai_client()
    prompt = f"Analyze this speech text for a presentation. Grade it (A-F), score pacing (1-10), and count fillers. JSON output. Text: {transcript}"
    
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- UTILS FOR UI ---
def delete_item(mod, type_, id_):
    data = load_data()
    if mod in data["Modules"]:
        items = data["Modules"][mod].get(type_, [])
        data["Modules"][mod][type_] = [i for i in items if i.get("id") != id_]
        save_data(data)

def add_manual_item(mod, type_, title, details, date):
    data = load_data()
    if mod not in data["Modules"]:
        data["Modules"][mod] = {"tasks": [], "events": [], "knowledge": []}
        
    new_id = len(data["Modules"][mod][type_]) + 1
    item = {"id": new_id, "title": title, "details": details, "date": date}
    data["Modules"][mod][type_].append(item)
    save_data(data)
