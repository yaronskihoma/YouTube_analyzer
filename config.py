import os
from googleapiclient.discovery import build
import streamlit as st

def get_api_key() -> str:
    """Get API key from various sources."""
    # Try Streamlit secrets first
    try:
        return st.secrets["youtube_api_key"]
    except:
        # Fall back to environment variable
        return os.getenv("YOUTUBE_API_KEY", "")

def validate_api_key(api_key: str) -> bool:
    """Validate YouTube API key."""
    if not api_key:
        return False
        
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.search().list(
            part="id",
            maxResults=1
        )
        request.execute()
        return True
    except:
        return False
