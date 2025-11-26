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
# HARDCODED TO CHINA TIME AS REQUESTED
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
    if not os.path.exists(DA
