def get_custom_css():
    return """
    <style>
        /* 1. ANIMATED NORTHERN LIGHTS BACKGROUND */
        .stApp {
            background: linear-gradient(-45deg, #020024, #090979, #1c0b36, #00d4ff);
            background-size: 400% 400%;
            animation: gradient 15s ease infinite;
            color: white;
        }

        @keyframes gradient {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        /* 2. SIDEBAR GLASSMORPHISM */
        section[data-testid="stSidebar"] {
            background-color: rgba(255, 255, 255, 0.05) !important;
            backdrop-filter: blur(20px);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        /* Sidebar Text Colors */
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] p {
            color: #ffffff !important;
        }

        /* 3. CARDS & CONTAINERS (The "Glass" Effect) */
        .stTextInput > div > div, .stTextArea > div > div, .stSelectbox > div > div {
            background-color: rgba(0, 0, 0, 0.3) !important;
            color: white !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            border-radius: 12px;
        }
        
        /* Event Cards in Weekly View */
        .event-card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 10px;
            color: white;
            transition: transform 0.2s;
        }
        .event-card:hover {
            transform: translateY(-2px);
            background: rgba(255, 255, 255, 0.15);
        }

        /* 4. HEADERS & FONTS */
        h1, h2, h3 {
            font-family: 'Helvetica Neue', sans-serif;
            font-weight: 700;
            background: -webkit-linear-gradient(#eee, #333);
            -webkit-background-clip: text;
            text-shadow: 0px 0px 20px rgba(255,255,255,0.3);
        }
        
        /* 5. BUTTONS */
        .stButton > button {
            background: linear-gradient(45deg, #FF0099, #493240);
            color: white;
            border: none;
            border-radius: 20px;
            padding: 0.5rem 1rem;
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            box-shadow: 0 0 15px rgba(255, 0, 153, 0.5);
            transform: scale(1.05);
        }

        /* 6. CHAT BUBBLES */
        .stChatMessage {
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
    </style>
    """
