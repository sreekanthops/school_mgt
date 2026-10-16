import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./school.db")
# If JWT_SECRET is not configured an ephemeral one is used (sessions reset on restart).
JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
CURRENT_YEAR = os.environ.get("CURRENT_ACADEMIC_YEAR", "2025-26")
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",")
    if o.strip()
]

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# SMTP for owner password-reset emails (use a Gmail App Password, not your real Gmail password).
# Leave empty to disable owner email recovery — security questions and the superadmin remain available.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")       # your Gmail address
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # Gmail App Password
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)   # defaults to SMTP_USER
