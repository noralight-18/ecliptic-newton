import os
import json
import datetime
import pytz
import base64
import uuid
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_openai_client():
    """Initialize and return the OpenAI client."""
    api_key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)

def get_beijing_time_str():
    """Returns current Beijing time as HH:MM string."""
    return datetime.datetime.now(BEIJING_TZ).strftime("%H:%M")

def get_current_date_str():
    """Returns current Beijing date as string."""
    return datetime.datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')

def get_current_context():
    """
    Determine the current context based on the schedule.json and current time (Beijing Time).
    """
    try:
        with open("schedule.json", "r") as f:
            schedule = json.load(f)
        
        now = datetime.datetime.now(BEIJING_TZ)
        day_name = now.strftime("%A")
        current_time = now.time()
        
        if day_name in schedule:
            for time_range, subject in schedule[day_name].items():
                try:
                    start_str, end_str = time_range.split("-")
                    start_time = datetime.datetime.strptime(start_str, "%H:%M").time()
                    end_time = datetime.datetime.strptime(end_str, "%H:%M").time()
                    
                    if start_time <= current_time <= end_time:
                        return f"In Class: {subject}"
                except ValueError:
                    continue
                    
        return "Free Time / General Admin"
    except:
        return "Unknown Context"

def get_current_module():
    """
    Returns the specific module name if currently in class, else 'General'.
    """
    context = get_current_context()
    if context.startswith("In Class: "):
        subject = context.replace("In Class: ", "").split(" [")[0].strip()
        return subject
    return "General"

def get_all_classes():
    """
    Returns a sorted list of all unique class names from schedule.json (Normalized).
    """
    try:
        with open("schedule.json", "r") as f:
            schedule = json.load(f)
        classes = set()
        for day in schedule.values():
            for class_name in day.values():
                clean_name = class_name.split(" [")[0].strip()
                classes.add(clean_name)
        return sorted(list(classes))
    except:
        return []

def load_data():
    """Load data from data.json."""
    if not os.path.exists("data.json"):
        return {"Modules": {}}
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {"Modules": {}}

def save_data(data):
    """Save data to data.json."""
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

def add_manual_item(module, item_type, title, details, date=None, label="Notes"):
    """
    Add an item manually to the database.
    """
    data = load_data()
    if "Modules" not in data:
        data["Modules"] = {}
    if module not in data["Modules"]:
        data["Modules"][module] = {"tasks": [], "knowledge": [], "events": []}
        
    new_item = {
        "id": str(uuid.uuid4()),
        "title": title,
        "details": details,
        "date": date if date else get_current_date_str(),
        "created_at": datetime.datetime.now().timestamp()
    }
    
    if item_type == "knowledge":
        new_item["label"] = label
        
    data["Modules"][module][item_type].append(new_item)
    save_data(data)
    return new_item

def delete_item(module, item_type, item_id):
    """
    Delete an item by ID.
    """
    data = load_data()
    if module in data["Modules"]:
        items = data["Modules"][module].get(item_type, [])
        data["Modules"][module][item_type] = [i for i in items if i.get("id") != item_id]
        save_data(data)

def transcribe_audio(audio_file, for_coach=False):
    """
    Transcribe audio using OpenAI Whisper.
    """
    client = get_openai_client()
    try:
        prompt = "Um, uh, like, so, okay, strictly transcribe verbatim." if for_coach else ""
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            prompt=prompt
        )
        return transcript.text
    except Exception as e:
        return f"Error during transcription: {str(e)}"

def process_assistant_input(text, manual_module=None, last_task_metadata=None):
    """
    Process text to categorize into Modules and Types.
    Handles Reformulation and Aggressive Merging.
    """
    client = get_openai_client()
    context = get_current_context()
    current_date_str = get_current_date_str()
    
    try:
        with open("schedule.json", "r") as f:
            schedule_json = f.read()
    except:
        schedule_json = "{}"

    # Aggressive Merging Logic
    should_merge = False
    merging_instruction = ""
    
    if last_task_metadata:
        time_diff = datetime.datetime.now().timestamp() - last_task_metadata.get("timestamp", 0)
        if time_diff < 60:
            should_merge = True
            last_title = last_task_metadata.get("title", "")
            last_details = last_task_metadata.get("details", "")
            merging_instruction = f"""
            AGGRESSIVE MERGING ACTIVE (User spoke again within 60s).
            PREVIOUS TASK: Title="{last_title}", Details="{last_details}"
            NEW INPUT: "{text}"
            
            INSTRUCTION: Combine the previous task and new input.
            Return action: "update".
            REFORMULATE the Title and Details to include the new info.
            """

    system_prompt = f"""
    You are Emily, an Executive OS.
    CURRENT DATE: {current_date_str} (Beijing Time).
    CONTEXT: {context}
    USER TIMETABLE: {schedule_json}
    
    {merging_instruction}
    
    INSTRUCTION:
    1. Analyze the input text.
    2. Classify it into a Module. If 'manual_module' is provided ({manual_module}), PREFER that module.
    3. Classify type: "tasks", "knowledge", "events".
    4. REFORMULATION: Extract structured data.
       - Title: Short, Actionable, Executive Style (e.g., "Study Finance"). NO raw transcripts.
       - Details: The full context/details.
       - Date: YYYY-MM-DD (Required for events/tasks). Default to today if unsure.
       - Label: For knowledge (e.g., "Notes", "Admin").
    
    OUTPUT JSON:
    {{
        "action": "create" | "update",
        "module_name": "Subject Name",
        "type": "tasks" | "knowledge" | "events",
        "title": "Executive Title",
        "details": "Full Details",
        "date": "YYYY-MM-DD",
        "label": "Label"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        # Update Data
        data = load_data()
        
        action = result.get("action", "create")
        module = result.get("module_name", manual_module if manual_module else "General")
        item_type = result.get("type", "knowledge")
        
        new_item = {
            "id": str(uuid.uuid4()),
            "title": result.get("title", "Untitled"),
            "details": result.get("details", text),
            "date": result.get("date", current_date_str),
            "created_at": datetime.datetime.now().timestamp()
        }
        
        if item_type == "knowledge":
            new_item["label"] = result.get("label", "Notes")
        
        if "Modules" not in data:
            data["Modules"] = {}
        if module not in data["Modules"]:
            data["Modules"][module] = {"tasks": [], "knowledge": [], "events": []}
            
        target_list = data["Modules"][module][item_type]
        
        if should_merge and action == "update" and target_list:
             # Overwrite last item (preserve ID if possible, or just replace)
            last_id = target_list[-1].get("id")
            new_item["id"] = last_id # Keep ID stable
            target_list[-1] = new_item
        else:
            target_list.append(new_item)
            
        save_data(data)
        
        # Return metadata for state update
        return {
            "title": new_item["title"],
            "details": new_item["details"],
            "module": module,
            "type": item_type,
            "timestamp": new_item["created_at"]
        }
        
    except Exception as e:
        return {"error": str(e)}

def analyze_image(image_file, manual_module="General"):
    """
    Analyze image using GPT-4o Vision.
    """
    client = get_openai_client()
    base64_image = base64.b64encode(image_file.getvalue()).decode('utf-8')
    current_date_str = get_current_date_str()
    
    system_prompt = f"""
    You are Emily. Extract text/insights.
    Classify into Module: {manual_module} (Preferred).
    Return JSON: {{"module_name": "{manual_module}", "title": "Short Title", "details": "Extracted text", "label": "Notes"}}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analyze this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        add_manual_item(
            module=result.get("module_name", manual_module),
            item_type="knowledge",
            title=result.get("title", "Image Note"),
            details=f"[IMAGE] {result.get('details', '')}",
            label=result.get("label", "Notes")
        )
        return result.get("details", "")
        
    except Exception as e:
        return f"Error: {str(e)}"

def analyze_speech_coach(text):
    """
    Analyze speech for filler words and pacing.
    """
    client = get_openai_client()
    system_prompt = """
    You are a Speech Coach. Analyze transcript.
    Return JSON: {"filler_count": int, "pacing_score": int (1-10), "grade": "A-F", "critique": "Feedback"}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"filler_count": 0, "pacing_score": 0, "grade": "N/A", "critique": "Error"}

def chat_with_emily(question, history):
    """
    Omniscient Chatbot with Action Capabilities.
    """
    client = get_openai_client()
    data = load_data()
    try:
        with open("schedule.json", "r") as f:
            schedule = json.load(f)
    except:
        schedule = {}
        
    current_date_str = get_current_date_str()
    
    system_prompt = f"""
    You are Emily, the Executive OS.
    TODAY IS: {current_date_str}. You are synchronized to Beijing Time.
    
    DATA: {json.dumps(data)}
    SCHEDULE: {json.dumps(schedule)}
    
    INSTRUCTION:
    Answer the user's question.
    
    ACTIONABLE MODE:
    If the user asks to ADD a task/event (e.g., "Add a test for Law tomorrow"), extract details and return JSON:
    {{
        "ACTION": "SAVE_TASK",
        "data": {{
            "module": "Subject",
            "type": "tasks" | "events",
            "title": "Short Title",
            "details": "Details",
            "date": "YYYY-MM-DD"
        }}
    }}
    
    Otherwise, return normal text.
    """
    
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": question}]
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        content = response.choices[0].message.content
        
        # Check for Action Signal
        try:
            if "ACTION" in content:
                # Try to parse JSON if it looks like JSON
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end]
                action_data = json.loads(json_str)
                if action_data.get("ACTION") == "SAVE_TASK":
                    d = action_data["data"]
                    add_manual_item(d["module"], d["type"], d["title"], d["details"], d["date"])
                    return f"✅ Done. Added '{d['title']}' to {d['module']}."
        except:
            pass
            
        return content
    except Exception as e:
        return f"Error: {str(e)}"
