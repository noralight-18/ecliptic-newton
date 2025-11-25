def get_custom_css():
    return """
    <style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    /* Global Font & Text Color */
    html, body, [class*="css"], .stMarkdown, .stCaption, p, h1, h2, h3, li, span, div {
        font-family: 'Inter', sans-serif;
        color: #ffffff !important;
    }
    
    /* Northern Lights Animated Gradient Background */
    .stApp {
        background: linear-gradient(-45deg, #021B79, #45217C, #0575E6, #00F260);
        background-size: 400% 400%;
        animation: gradient 15s ease infinite;
    }
    
    @keyframes gradient {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    /* Sidebar Background (Glassmorphic) */
    [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Sidebar Expanders (Glass Effect) */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.1) !important;
        color: white !important;
        border-radius: 10px;
    }
    .streamlit-expanderContent {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0 0 10px 10px;
    }
    
    /* Glassmorphic Containers */
    .glass-container, div[data-testid="stAudioInput"], div[data-testid="stCameraInput"], div.stInfo, div.stWarning, div.stSuccess, div[data-testid="stChatInput"] {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(12px);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 15px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        margin-bottom: 15px;
    }
    
    /* Event Card Styling */
    .event-card {
        background: rgba(255, 255, 255, 0.1);
        border-left: 4px solid #fff;
        padding: 10px;
        margin-bottom: 10px;
        border-radius: 5px;
    }
    
    /* Input Fields */
    .stTextInput input, .stChatInput textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: rgba(255, 255, 255, 0.1) !important;
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
    }
    
    /* Headers */
    h1, h2, h3 {
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    </style>
    """
