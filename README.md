# Emily OS: The Executive Assistant

Emily is a comprehensive Executive Operating System designed to manage your schedule, tasks, knowledge, and presentation skills. It features a "Cool Executive" theme with a Northern Lights gradient and glassmorphism UI.

## Features

- **🎙️ Capture**: Voice and visual input for quick task and note capture.
- **📅 Calendar**: Weekly planner with manual event entry and schedule integration.
- **✅ Tasks**: Kanban-style task board with manual entry and module filtering.
- **🧠 Knowledge**: Organized knowledge base grouped by labels.
- **🗣️ Coach**: Speech analysis tool for practicing presentations (pacing, filler words).
- **💬 Omniscient Chat**: Context-aware chatbot that can perform actions (add tasks/events).

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    - Copy `.env.example` to `.env`.
    - Add your `OPENAI_API_KEY` to `.env`.

3.  **Run the Application**:
    ```bash
    streamlit run main.py
    ```

## Files

- `main.py`: The main Streamlit application.
- `utils.py`: Core logic, data handling, and AI integration.
- `styles.py`: Custom CSS for the "Cool Executive" theme.
- `schedule.json`: Your weekly class schedule.
- `data.json`: Database for tasks, events, and knowledge.

## Usage

- **Navigation**: Use the sidebar to switch between views.
- **Today's Focus**: Check off items in the sidebar to mark them as done.
- **Voice Commands**: Use the "Capture" tab to speak tasks naturally (e.g., "Remind me to study for Law tomorrow").
- **Chat**: Use the chat at the bottom to ask questions or command Emily to do things.
