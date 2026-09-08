"""Lazy Gemini client — reads GEMINI_API_KEY from backend/.env (gitignored,
never committed). Raises a clear error at call time, not import time, so the
rest of the app works fine with no key configured."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODEL = "gemini-3.6-flash"


@lru_cache
def get_client():
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in backend/.env")
    return genai.Client(api_key=api_key)
