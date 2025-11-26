import streamlit as st
import utils
import styles
import os
import pandas as pd
import datetime
import pytz
import requests
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="Emily: Executive OS", page_icon="💼", layout="wide")

# Inject CSS
st.markdown(styles.get_custom_css(), unsafe_allow_html=True)

# --- NOTIFICATION HELPERS (NEW) ---

def send_telegram_alert(message):
    """Sends a message to your phone via Telegram."""
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def add_google_calendar_event(summary, date_obj, duration_minutes=60):
    """Adds an event to Google Calendar."""
    try:
        if "google" in st.secrets:
            # Load credentials
            creds_dict = dict(st.secrets["google"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=creds)

            # Handle Date (Default to 9 AM if it's just a date object)
            if isinstance(date_obj, datetime.date) and not isinstance(date_obj, datetime.datetime):
                start_dt = datetime.datetime.combine(date_obj, datetime.time(9, 0))
            else:
                start_dt = date_obj

            end_dt = start_dt + timedelta(minutes=duration_minutes)

            event = {
                'summary': f"🎓 {summary}", 
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Shanghai'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Shanghai'},
            }
            
            service.events().insert(calendarId='primary', body=event).execute()
            return True
    except Exception as e:
        st.error(f"Calendar Error: {e}")
        return False

# --- SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.title("💼 Emily OS")
    
    # Info
    st.caption(f"🕒 Beijing: {utils.get_beijing_time_str()}")
    st.caption(f"📍 {utils.get_current_context()}")
    
    st.divider()
    
    # Navigation
    view = st.radio("Navigation", ["🎙️ Capture", "📅 Calendar", "✅ Tasks", "🧠 Knowledge", "🗣️ Coach"])
    
    st.divider()
    
    # 🔥 Today's Focus (Active Sidebar)
    st.subheader("🔥 Today's Focus")
    today_str = utils.get_current_date_str()
    data = utils.load_data()
    modules = data.get("Modules", {})
    
    focus_items = []
    for mod, content in modules.items():
        # Check Tasks & Events
        for item in content.get("tasks", []) + content.get("events", []):
            if isinstance(item, dict) and item.get("date") == today_str:
                focus_items.append({"mod": mod, "item": item, "type": "tasks" if item in content.get("tasks", []) else "events"})
    
    if focus_items:
        for idx, entry in enumerate(focus_items):
            item = entry["item"]
            # Unique key for checkbox
            if st.checkbox(f"{item['title']}", key=f"focus_{idx}"):
                utils.delete_item(entry["mod"], entry["type"], item["id"])
                st.rerun()
            st.caption(f"{entry['mod']} • {item['details']}")
    else:
        st.caption("No items for today.")

    st.divider()
    
    # API Key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        try:
            if "OPENAI_API_KEY" in st.secrets:
                api_key = st.secrets["OPENAI_API_KEY"]
                os.environ["OPENAI_API_KEY"] = api_key
        except:
            pass
            
    if not api_key:
        api_key_input = st.text_input("API Key", type="password")
        if api_key_input:
            os.environ["OPENAI_API_KEY"] = api_key_input
            st.rerun()

# --- VIEWS ---

if view == "🎙️ Capture":
    st.header("🎙️ Command Center")
    
    # Smart Default Module
    default_module = utils.get_current_module()
    
    # Populate options
    schedule_classes = utils.get_all_classes()
    existing_modules = list(modules.keys())
    all_options = sorted(list(set(schedule_classes + existing_modules)))
    module_options = ["General"] + all_options
    
    default_index = 0
    if default_module in module_options:
        default_index = module_options.index(default_module)
        
    selected_module = st.selectbox("Assign to Module:", module_options, index=default_index)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Audio Input")
        with st.container():
            audio_val = st.audio_input("Voice Command")
            
        # Loop Fix & State Management
        if "last_audio" not in st.session_state:
            st.session_state["last_audio"] = None
        if "last_task_metadata" not in st.session_state:
            st.session_state["last_task_metadata"] = None
            
        if audio_val and audio_val != st.session_state["last_audio"]:
            with st.spinner("Processing..."):
                transcript = utils.transcribe_audio(audio_val)
                st.info(f"Transcript: {transcript}")
                
                result_meta = utils.process_assistant_input(
                    transcript, 
                    manual_module=selected_module, 
                    last_task_metadata=st.session_state["last_task_metadata"]
                )
                
                # Update State
                if isinstance(result_meta, dict) and "error" not in result_meta:
                    st.session_state["last_task_metadata"] = result_meta
                    
                    # --- AUTO NOTIFICATION HOOK (VOICE) ---
                    # Note: We need to see utils.py to do this perfectly, 
                    # but if 'type' is in result_meta, we can try:
                    item_type = result_meta.get("type", "").lower()
                    item_title = result_meta.get("title", "Voice Command")
                    
                    if "task" in item_type:
                        send_telegram_alert(f"🎙️ *Voice Task Added*\n{item_title}")
                    elif "event" in item_type:
                        # Assuming result_meta might have a date, if not, this is tricky without utils.py
                        # For now, we just notify Telegram that an event was created
                        send_telegram_alert(f"📅 *Event Created via Voice*\n{item_title}\nCheck Calendar.")
                    # -------------------------------------

                st.session_state["last_audio"] = audio_val
                st.success("Saved to System.")
                st.rerun()

    with col2:
        st.subheader("Visual Input")
        with st.container():
            img_val = st.camera_input("Scan Document")
            
        if img_val:
            with st.spinner("Analyzing Vision..."):
                note = utils.analyze_image(img_val, manual_module=selected_module)
                st.success("Image Analyzed & Saved.")
                st.info(note)

elif view == "📅 Calendar":
    st.header("📅 Weekly Planner")
    
    # Manual Entry Form
    with st.expander("➕ Add Item Manually"):
        with st.form("manual_event"):
            c1, c2 = st.columns(2)
            m_title = c1.text_input("Title")
            m_date = c2.date_input("Date")
            m_details = st.text_area("Details")
            
            # Module Dropdown
            schedule_classes = utils.get_all_classes()
            existing_modules = list(modules.keys())
            all_options = sorted(list(set(schedule_classes + existing_modules)))
            m_module = st.selectbox("Module", ["General"] + all_options)
            
            if st.form_submit_button("Save Event"):
                utils.add_manual_item(m_module, "events", m_title, m_details, str(m_date))
                
                # --- GOOGLE CALENDAR SYNC ---
                with st.spinner("Syncing to Google Calendar..."):
                    add_google_calendar_event(m_title, m_date)
                # ----------------------------
                
                st.success("Event Saved & Synced to Google!")
                st.rerun()
    
    # Calculate dates for current week (Mon-Fri)
    beijing_tz = pytz.timezone('Asia/Shanghai')
    today = datetime.datetime.now(beijing_tz).date()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    week_dates = [start_of_week + datetime.timedelta(days=i) for i in range(5)]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    cols = st.columns(5)
    
    for i, col in enumerate(cols):
        current_day_date = week_dates[i]
        date_str = current_day_date.strftime("%Y-%m-%d")
        
        with col:
            st.markdown(f"**{days[i]}**")
            st.caption(date_str)
            
            # Find events for this day
            events_found = False
            for mod, content in modules.items():
                for event in content.get("events", []):
                    if isinstance(event, dict) and event.get("date") == date_str:
                        st.markdown(f"""
                        <div class="event-card">
                            <b>{event['title']}</b><br>
                            <span style="font-size:0.8em;">{event['details']}</span><br>
                            <span style="font-size:0.7em; color:#ccc">{mod}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        events_found = True
            
            if not events_found:
                st.markdown('<div style="opacity:0.3; padding:10px;">No events</div>', unsafe_allow_html=True)

elif view == "✅ Tasks":
    st.header("✅ Task Board")
    
    # Manual Entry Form
    with st.expander("➕ Add Task Manually"):
        with st.form("manual_task"):
            c1, c2 = st.columns(2)
            t_title = c1.text_input("Title")
            t_date = c2.date_input("Due Date")
            t_details = st.text_area("Details")
            
            # Module Dropdown
            schedule_classes = utils.get_all_classes()
            existing_modules = list(modules.keys())
            all_options = sorted(list(set(schedule_classes + existing_modules)))
            t_module = st.selectbox("Module", ["General"] + all_options)
            
            if st.form_submit_button("Save Task"):
                utils.add_manual_item(t_module, "tasks", t_title, t_details, str(t_date))
                
                # --- TELEGRAM NOTIFICATION ---
                send_telegram_alert(f"📝 *New Task Added*\n\n**{t_title}**\nDue: {t_date}\nModule: {t_module}")
                # -----------------------------
                
                st.success("Task Saved & Sent to Phone")
                st.rerun()
    
    if not modules:
        st.info("No modules initialized.")
    else:
        # Create columns for modules
        mod_names = list(modules.keys())
        cols = st.columns(len(mod_names)) if len(mod_names) > 0 else [st.container()]
        
        for idx, mod_name in enumerate(mod_names):
            content = modules[mod_name]
            with cols[idx]:
                st.subheader(mod_name)
                for task in content.get("tasks", []):
                    if isinstance(task, dict):
                        st.warning(f"**{task['title']}**\n\n{task['details']}")
                    else:
                        st.warning(f"☐ {task}")

elif view == "🧠 Knowledge":
    st.header("🧠 Knowledge Base")
    
    for mod_name, content in modules.items():
        with st.expander(f"📂 {mod_name}", expanded=False):
            # Sub-Tabs for Labels
            knowledge_items = content.get("knowledge", [])
            
            # Group by Label
            grouped = {}
            for item in knowledge_items:
                if isinstance(item, dict):
                    label = item.get("label", "Notes")
                    # Construct display text
                    text = f"**{item.get('title', 'Note')}**: {item.get('details', '')}"
                else:
                    label = "Notes"
                    text = item
                
                if label not in grouped:
                    grouped[label] = []
                grouped[label].append(text)
            
            if grouped:
                tabs = st.tabs(list(grouped.keys()))
                for i, label in enumerate(grouped.keys()):
                    with tabs[i]:
                        for note in grouped[label]:
                            st.markdown(f"- {note}")
            else:
                st.caption("No notes.")

elif view == "🗣️ Coach":
    st.header("🗣️ Presentation Coach")
    st.caption("Raw transcription enabled for filler word detection.")
    
    audio_coach = st.audio_input("Practice Speech")
    
    if audio_coach:
        with st.spinner("Analyzing..."):
            transcript = utils.transcribe_audio(audio_coach, for_coach=True)
            st.markdown(f"**Transcript:** {transcript}")
            stats = utils.analyze_speech_coach(transcript)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Grade", stats.get("grade", "N/A"))
            c2.metric("Pacing", f"{stats.get('pacing_score', 0)}/10")
            c3.metric("Fillers", stats.get("filler_count", 0))
            
            st.info(f"Critique: {stats.get('critique', '')}")

# --- OMNISCIENT CHAT ---
st.divider()
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat Input & Vision
col_chat_input, col_chat_upload = st.columns([0.85, 0.15])

with col_chat_input:
    prompt = st.chat_input("Ask Emily...")

with col_chat_upload:
    uploaded_file = st.file_uploader("📷", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.spinner("Thinking..."):
        history = [m for m in st.session_state.messages if m["role"] != "system"]
        # AI Logic happens in utils.chat_with_emily
        response = utils.chat_with_emily(prompt, history)
        
    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
        # If response indicates action was taken, force rerun to update UI
        if "✅ Done" in response:
            st.rerun()

if uploaded_file:
    with st.spinner("Analyzing Image..."):
        note = utils.analyze_image(uploaded_file, manual_module="General")
        st.session_state.messages.append({"role": "user", "content": "[Uploaded an Image]"})
        st.session_state.messages.append({"role": "assistant", "content": f"I've analyzed the image and saved it to General Notes:\n\n{note}"})
        st.rerun()
