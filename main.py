import streamlit as st
import utils
import styles
import os
import datetime
import pytz

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Andy OS", page_icon="👓", layout="wide")

# Inject CSS (Glassmorphism)
st.markdown(styles.get_custom_css(), unsafe_allow_html=True)

# --- 2. MORNING WAKE UP CALL ---
# This checks if it's a new day and sends the Telegram Briefing if needed
utils.check_and_send_briefing()

# --- 3. SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.title("👓 Andy OS")
    
    # Info
    st.caption(f"🕒 Beijing: {utils.get_beijing_time_str()}")
    st.caption(f"📍 {utils.get_current_context()}")
    
    st.divider()
    
    # Navigation
    view = st.radio("Navigation", ["🎙️ Command Center", "📅 Calendar", "✅ Tasks", "🧠 Knowledge", "🗣️ Coach"])
    
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
            st.caption(f"{entry['mod']} • {item.get('details', '')}")
    else:
        st.caption("No items for today.")

    st.divider()
    
    # API Key Handling
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

# --- 4. VIEWS ---

if view == "🎙️ Command Center":
    st.header("🎙️ Command Center")
    
    # Smart Default Module
    default_module = utils.get_current_module()
    
    # Populate options
    schedule_classes = utils.get_all_classes()
    existing_modules = list(modules.keys())
    all_options = sorted(list(set(schedule_classes + existing_modules)))
    # Ensure General is first
    if "General" in all_options: all_options.remove("General")
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
            
        # State Management
        if "last_audio" not in st.session_state:
            st.session_state["last_audio"] = None
            
        if audio_val and audio_val != st.session_state["last_audio"]:
            with st.spinner("Processing..."):
                transcript = utils.transcribe_audio(audio_val)
                st.info(f"Transcript: {transcript}")
                
                # Send to AI Router
                result_meta = utils.process_assistant_input(
                    transcript, 
                    manual_module=selected_module
                )
                
                # Display Result
                if isinstance(result_meta, dict) and "error" not in result_meta:
                    if result_meta.get("type") == "event":
                        st.success(f"📅 Scheduled: {result_meta.get('title')}")
                    elif result_meta.get("type") == "note":
                        st.success(f"🧠 Note Saved: {result_meta.get('title')}")
                    else:
                        st.success(f"✅ Task Added: {result_meta.get('title')}")
                        
                    if result_meta.get("telegram_sent"):
                        st.toast("📲 Sent to Phone")
                    
                st.session_state["last_audio"] = audio_val
                st.rerun()

    with col2:
        st.subheader("Visual Input")
        with st.container():
            img_val = st.camera_input("Scan Document")
            
        if img_val:
            with st.spinner("Transcribing Verbatim..."):
                note = utils.analyze_image(img_val, manual_module=selected_module)
                st.success("Document Saved to Knowledge Base.")
                with st.expander("View Transcription"):
                    st.write(note)

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
                
                # Sync to Google
                with st.spinner("Syncing..."):
                    iso = f"{m_date}T09:00:00"
                    utils.add_google_calendar_event(m_title, iso)
                
                st.success("Event Saved & Synced")
                st.rerun()
    
    # Calendar Grid View
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
            
            # Find events
            events_found = False
            for mod, content in modules.items():
                for event in content.get("events", []):
                    if isinstance(event, dict) and event.get("date") == date_str:
                        st.markdown(f"""
                        <div class="event-card">
                            <b>{event['title']}</b><br>
                            <span style="fon
