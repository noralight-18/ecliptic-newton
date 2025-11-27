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
                            <span style="font-size:0.8em;">{event.get('time', '')}</span><br>
                            <span style="font-size:0.7em; color:#ccc">{mod}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        events_found = True
            
            if not events_found:
                st.markdown('<div style="opacity:0.3; padding:10px;">Empty</div>', unsafe_allow_html=True)

elif view == "✅ Tasks":
    st.header("✅ Task Board")
    
    # Manual Entry
    with st.expander("➕ Add Task Manually"):
        with st.form("manual_task"):
            c1, c2 = st.columns(2)
            t_title = c1.text_input("Title")
            t_date = c2.date_input("Due Date")
            t_details = st.text_area("Details")
            
            schedule_classes = utils.get_all_classes()
            all_options = sorted(list(set(schedule_classes + list(modules.keys()))))
            t_module = st.selectbox("Module", ["General"] + all_options)
            
            if st.form_submit_button("Save Task"):
                utils.add_manual_item(t_module, "tasks", t_title, t_details, str(t_date))
                st.success("Task Saved")
                st.rerun()
    
    if not modules:
        st.info("No active modules.")
    else:
        # Kanban Columns
        mod_names = list(modules.keys())
        cols = st.columns(len(mod_names)) if len(mod_names) > 0 else [st.container()]
        
        for idx, mod_name in enumerate(mod_names):
            content = modules[mod_name]
            with cols[idx]:
                st.subheader(mod_name)
                for task in content.get("tasks", []):
                    if isinstance(task, dict):
                        st.warning(f"**{task['title']}**\n\n{task.get('date', '')}")
                    else:
                        st.warning(f"☐ {task}")

elif view == "🧠 Knowledge":
    st.header("🧠 Knowledge Base")
    
    for mod_name, content in modules.items():
        with st.expander(f"📂 {mod_name}", expanded=False):
            knowledge_items = content.get("knowledge", [])
            
            if knowledge_items:
                for item in knowledge_items:
                    st.markdown(f"#### {item.get('title', 'Note')}")
                    st.caption(item.get('date', ''))
                    st.write(item.get('details', ''))
                    st.divider()
            else:
                st.caption("No notes.")

elif view == "🗣️ Coach":
    st.header("🗣️ Presentation Coach")
    
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

# Chat Input & Vision Upload
col_chat_input, col_chat_upload = st.columns([0.85, 0.15])

with col_chat_input:
    prompt = st.chat_input("Ask Andy...")

with col_chat_upload:
    uploaded_file = st.file_uploader("📷", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.spinner("Working..."):
        history = [m for m in st.session_state.messages if m["role"] != "system"]
        response = utils.chat_with_emily(prompt, history)
        
    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
        if "✅" in response: # If action taken, refresh UI
            st.rerun()

if uploaded_file:
    with st.spinner("Transcribing..."):
        note = utils.analyze_image(uploaded_file, manual_module="General")
        st.session_state.messages.append({"role": "user", "content": "[Uploaded Document]"})
        st.session_state.messages.append({"role": "assistant", "content": f"✅ I've transcribed that document into your Knowledge Base.\n\n**Preview:**\n{note[:200]}..."})
        st.rerun()
