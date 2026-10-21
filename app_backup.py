"""NU10 Interview Scheduler API.

Run locally:
    python -m uvicorn app:app --host 0.0.0.0 --port 8000

Email is sent through Gmail SMTP using SMTP_USER and SMTP_PASS from .env.
"""

import html
import json
import os
import secrets
import smtplib
from datetime import datetime, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

APP_NAME = "NU10 Interview Scheduler"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'nu10_scheduler.db'}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

IST = ZoneInfo("Asia/Kolkata")


def format_ist(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(64), unique=True, index=True, nullable=False)
    candidate_name = Column(String(200), nullable=False)
    candidate_email = Column(String(320), nullable=False)
    candidate_phone = Column(String(80), default="")
    job_title = Column(String(200), nullable=False)
    interviewer_name = Column(String(200), nullable=False)
    interviewer_email = Column(String(320), nullable=False)
    slots_json = Column(Text, nullable=False)
    selected_slot = Column(String(80), nullable=True)
    meeting_url = Column(String(500), nullable=True)
    status = Column(String(100), default="Invitation queued", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    booked_at = Column(DateTime(timezone=True), nullable=True)
    invitation_sent = Column(Boolean, default=False)
    confirmation_sent = Column(Boolean, default=False)
    reminder_24_sent = Column(Boolean, default=False)
    reminder_1_sent = Column(Boolean, default=False)
    reminder_15_sent = Column(Boolean, default=False)
    last_error = Column(Text, default="")


Base.metadata.create_all(bind=engine)
app = FastAPI(title=APP_NAME, version="1.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
security = HTTPBasic()
scheduler = AsyncIOScheduler(timezone="UTC")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def admin_auth(credentials: HTTPBasicCredentials = Depends(security)):
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_pass = os.getenv("ADMIN_PASSWORD", "")

    if not expected_pass:
        raise HTTPException(
            status_code=503,
            detail="Set ADMIN_PASSWORD in .env before using admin APIs."
        )

    ok = (
        secrets.compare_digest(credentials.username, expected_user)
        and secrets.compare_digest(credentials.password, expected_pass)
    )

    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Incorrect admin login",
            headers={"WWW-Authenticate": "Basic"}
        )

    return credentials.username