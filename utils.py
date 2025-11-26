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
USER_TIMEZONE = 'Asia/Shanghai' 
BEIJING_TZ = pytz.timezone(USER_TIMEZONE)

def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    if api_key:
        return OpenAI(api_key=api_key)
    return None

# --- DATABASE HELPERS ---
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
    if 9 <= h < 18: return "Working"
    return "Free Time"

def get_all_classes():
    return ["Business Law", "Strategic Management", "Marketing", "Finance"]

def get_current_module():
    return "General"

# --- NOTIFICATIONS ---
def send_telegram_alert(message):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def add_google_calendar_event(summary, start_iso, duration_minutes=60):
    try:
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            # Target the email in secrets, or default to the robot's calendar
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
                'start': {'dateTime': start_dt.isofo
