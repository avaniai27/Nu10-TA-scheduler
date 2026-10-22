
import os, json, secrets, requests
import requests
import re
import json
from io import BytesIO
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()
APP_NAME = "NU10 Interview Scheduler"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nu10_scheduler.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def format_ist(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if value.tzinfo is None:
        # Treat timezone-naive stored values as UTC.
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
    status = Column(String(60), default="Invitation queued", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    booked_at = Column(DateTime(timezone=True), nullable=True)
    invitation_sent = Column(Boolean, default=False)
    confirmation_sent = Column(Boolean, default=False)
    reminder_24_sent = Column(Boolean, default=False)
    reminder_1_sent = Column(Boolean, default=False)
    reminder_15_sent = Column(Boolean, default=False)
    last_error = Column(Text, default="")

Base.metadata.create_all(bind=engine)
app = FastAPI(title=APP_NAME, version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
scheduler = AsyncIOScheduler(timezone="UTC")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SlotIn(BaseModel):
    datetime: datetime

class InterviewIn(BaseModel):
    candidate_name: str = Field(min_length=1, max_length=200)
    candidate_email: EmailStr
    candidate_phone: str = ""
    job_title: str = Field(min_length=1, max_length=200)
    interviewer_name: str = Field(min_length=1, max_length=200)
    interviewer_email: EmailStr
    slots: list[SlotIn] = Field(min_length=1, max_length=10)

def base_url():
    return os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

def fmt_slot(value):
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = value

    # Always display interview times in India Standard Time.
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    dt = dt.astimezone(ZoneInfo("Asia/Kolkata"))

    return dt.strftime("%a, %d %b %Y at %I:%M %p IST")






def send_email(to, subject, html):
    """Send HTML email using the Gmail API."""
    import base64
    from email.mime.text import MIMEText
    from email.utils import formataddr
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/gmail.send"]
    token_json = os.getenv("GMAIL_TOKEN_JSON", "").strip()
    token_path = os.path.join(os.path.dirname(__file__), "token.json")

    # Use Render's environment variable when available;
    # otherwise use the local token.json file.
    if token_json:
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(token_json),
                scopes
            )
        except Exception as exc:
            raise RuntimeError(
                "GMAIL_TOKEN_JSON is invalid. Check its Render environment value."
            ) from exc
    elif os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(
            token_path,
            scopes
        )
    else:
        raise RuntimeError(
            "Gmail credentials are missing. Configure GMAIL_TOKEN_JSON on Render."
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # Persist refreshed credentials locally only.
        if not token_json:
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

    if not creds.valid:
        raise RuntimeError(
            "Gmail authorization is invalid or expired. Reauthorize Gmail."
        )

    sender = "avaninchal@gmail.com"

    message = MIMEText(html, "html", "utf-8")
    message["to"] = to
    message["subject"] = subject
    message["from"] = formataddr(("NU10 Talent Acquisition", sender))

    raw = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    try:
        service = build(
            "gmail",
            "v1",
            credentials=creds,
            cache_discovery=False
        )

        result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        print(
            f"Gmail API sent email to {to}; "
            f"message ID: {result['id']}"
        )

        return {
            "ok": True,
            "to": to,
            "provider": "gmail_api"
        }

    except Exception as exc:
        print(
            f"GMAIL API FAILED for {to}: "
            f"{type(exc).__name__}: {exc}"
        )
        raise RuntimeError(f"Gmail API failed: {exc}") from exc

def email_shell(content):
    logo_path = os.path.join("static", "nu10logo.jpg")

    if os.path.isfile(logo_path):
        logo_html = (
            '<img src="cid:nu10logo" alt="NU10" '
            'style="width:170px;max-width:100%;height:auto;display:block">'
        )
    else:
        logo_html = (
            f'<img src="{base_url()}/static/nu10logo.jpg" alt="NU10" '
            'style="width:170px;max-width:100%;height:auto;display:block">'
        )

    return f"""<!doctype html>
<html>
<body style="margin:0;background:#f3f6fb;font-family:Arial,sans-serif;color:#172033">
<div style="max-width:640px;margin:24px auto;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e5eaf2">
<div style="padding:24px 28px;border-bottom:1px solid #edf0f5">
{logo_html}
</div>
<div style="padding:28px;line-height:1.6">{content}</div>
<div style="padding:18px 28px;background:#f8fafc;color:#667085;font-size:12px">
This message was sent by NU10 Talent Acquisition. If you believe you received it in error, please contact the sender.
</div>
</div>
</body>
</html>"""


def invitation_html(iv):
    slots = json.loads(iv.slots_json)
    buttons = ""
    for i, slot in enumerate(slots):
        url = f"{base_url()}/book/{iv.public_id}/{i}"
        buttons += f'<p style="margin:12px 0"><a href="{url}" style="display:block;text-decoration:none;background:#168de2;color:#fff;padding:13px 16px;border-radius:8px;text-align:center;font-weight:bold">{fmt_slot(slot["datetime"])}</a></p>'
    content = f"""<h2 style="margin-top:0">Interview invitation</h2>
    <p>Hello {iv.candidate_name},</p><p>Thank you for your interest in the <b>{iv.job_title}</b> opportunity. We would like to invite you to an interview.</p>
    <p>NU10 helps organizations build AI-powered solutions that make work more intelligent and efficient. Our team focuses on practical innovation and helping businesses solve meaningful problems with technology.</p>
    <p>Please select one of the available interview times below. Selecting a time confirms your interview booking.</p>{buttons}
    <p>If none of these times works for you, please contact the Talent Acquisition team.</p><p>Regards,<br><b>NU10 Talent Acquisition</b></p>"""
    return email_shell(content)

def confirmation_html(iv, recipient_name, is_candidate):
    slot = fmt_slot(iv.selected_slot)
    content = f"""<h2 style="margin-top:0">Interview confirmed</h2><p>Hello {recipient_name},</p>
    <p>The interview for <b>{iv.candidate_name}</b> for <b>{iv.job_title}</b> has been scheduled.</p>
    <div style="background:#f4f8fc;padding:16px;border-radius:8px"><b>Date and time</b><br>{slot}<br><br><b>Candidate</b>: {iv.candidate_name}<br><b>Interviewer</b>: {iv.interviewer_name}</div>
    <p><a href="{iv.meeting_url}" style="display:inline-block;background:#168de2;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:bold">Join interview meeting</a></p>
    <p>Please keep this email for your records.</p><p>Regards,<br><b>NU10 Talent Acquisition</b></p>"""
    return email_shell(content)

def notify_ta_html(iv, heading, body):
    return email_shell(f"<h2>{heading}</h2><p>{body}</p><p><b>Candidate:</b> {iv.candidate_name}<br><b>Role:</b> {iv.job_title}<br><b>Interviewer:</b> {iv.interviewer_name}<br><b>Status:</b> {iv.status}</p>")

def public_view(iv):
    return {
        "id": iv.id, "public_id": iv.public_id, "candidate_name": iv.candidate_name,
        "candidate_email": iv.candidate_email, "candidate_phone": iv.candidate_phone,
        "job_title": iv.job_title, "interviewer_name": iv.interviewer_name,
        "interviewer_email": iv.interviewer_email, "slots": json.loads(iv.slots_json),
        "selected_slot": iv.selected_slot, "selected_slot_display": fmt_slot(iv.selected_slot) if iv.selected_slot else None,
        "meeting_url": iv.meeting_url, "status": iv.status, "created_at": iv.created_at.isoformat() if iv.created_at else None,
        "booked_at": iv.booked_at.isoformat() if iv.booked_at else None, "invitation_sent": iv.invitation_sent,
        "confirmation_sent": iv.confirmation_sent, "last_error": iv.last_error
    }

@app.on_event("startup")
async def startup():
    if not scheduler.running:
        scheduler.add_job(reminder_scan, "interval", minutes=1, id="reminder_scan", replace_existing=True)
        scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)

@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME}

@app.post("/resume/extract")
async def extract_resume(file: UploadFile = File(...)):
    filename = (file.filename or "").lower()

    if not filename.endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Upload a PDF, DOCX, or TXT resume."
        )

    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Resume must be smaller than 5 MB."
        )

    try:
        if filename.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )

        elif filename.endswith(".docx"):
            from docx import Document
            document = Document(BytesIO(content))
            text = "\n".join(
                paragraph.text for paragraph in document.paragraphs
            )

        else:
            text = content.decode("utf-8", errors="replace")

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this resume. Try another file."
        ) from exc

    email_match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text
    )

    phone_match = re.search(
        r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)",
        text
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # Best-effort name detection from the first few lines.
    candidate_name = ""
    for line in lines[:10]:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if (
            len(cleaned) <= 70
            and re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", cleaned)
            and len(cleaned.split()) >= 2
            and cleaned.lower() not in {
                "curriculum vitae", "resume", "professional summary"
            }
        ):
            candidate_name = cleaned
            break

    return {
        "candidate_name": candidate_name,
        "candidate_email": email_match.group(0) if email_match else "",
        "candidate_phone": phone_match.group(0).strip() if phone_match else "",
        "message": "Resume processed. Review the extracted details."
    }


@app.post("/interviews/start")
def start_interview(data: dict, db=Depends(get_db)):
    slots = []
    now = datetime.now().astimezone()
    seen = set()

    raw_slots = data.get("slots", [])
    for item in raw_slots:
        raw_dt = item.get("datetime") if isinstance(item, dict) else item
        if not raw_dt:
            continue

        dt = datetime.fromisoformat(str(raw_dt))
        if dt.tzinfo is None:
            dt = dt.astimezone()

        if dt <= now:
            raise HTTPException(400, "All interview slots must be in the future.")

        normalized = dt.isoformat()
        if normalized not in seen:
            slots.append({"datetime": normalized})
            seen.add(normalized)

    if not slots:
        raise HTTPException(400, "Add at least one future slot.")

    required = [
    "candidate_name", "candidate_email",
    "job_title", "interviewer_name", "interviewer_email"
]
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        raise HTTPException(400, "Missing required fields: " + ", ".join(missing))

    public_id = secrets.token_urlsafe(24)
    iv = Interview(
        public_id=public_id,
        candidate_name=data["candidate_name"].strip(),
        candidate_email=str(data["candidate_email"]).strip(),
        candidate_phone=str(data["candidate_phone"]).strip(),
        job_title=data["job_title"].strip(),
        interviewer_name=data["interviewer_name"].strip(),
        interviewer_email=str(data["interviewer_email"]).strip(),
        slots_json=json.dumps(slots),
        status="Invitation queued"
    )

    db.add(iv)
    db.commit()
    db.refresh(iv)

    try:
        send_email(
            iv.candidate_email,
            f"Interview invitation: {iv.job_title} | NU10",
            invitation_html(iv)
        )
        iv.invitation_sent = True
        iv.status = "Awaiting candidate selection"
        iv.last_error = ""
    except Exception as e:
        iv.status = "Email failed"
        iv.last_error = str(e)[:1000]

    db.commit()
    db.refresh(iv)

    return {
        "interview": public_view(iv),
        "email_sent": iv.invitation_sent,
        "message": (
            "Invitation sent."
            if iv.invitation_sent
            else "Interview saved, but invitation email failed. Check email settings."
        )
    }

@app.get("/book/{public_id}/{slot_index}", response_class=HTMLResponse)
def book_slot(public_id: str, slot_index: int, db=Depends(get_db)):
    iv = db.query(Interview).filter_by(public_id=public_id).with_for_update().first()
    if not iv:
        raise HTTPException(404, "This booking link is invalid.")
    if iv.selected_slot:
        return HTMLResponse(f"<html><body style='font-family:Arial;padding:40px'><h2>This interview is already booked</h2><p>Selected time: {fmt_slot(iv.selected_slot)}</p></body></html>", status_code=409)
    slots = json.loads(iv.slots_json)
    if slot_index < 0 or slot_index >= len(slots):
        raise HTTPException(404, "This slot does not exist.")
    selected = slots[slot_index]["datetime"]
    if datetime.fromisoformat(selected) <= datetime.now().astimezone():
        raise HTTPException(410, "This slot has passed. Please contact Talent Acquisition.")
    iv.selected_slot = selected
    iv.booked_at = datetime.now(timezone.utc)
    iv.meeting_url = f"https://meet.jit.si/NU10-Interview-{iv.public_id[:12]}"
    iv.status = "Interview scheduled"
    db.commit(); db.refresh(iv)
    errors = []
    try:
        send_email(iv.candidate_email, f"Interview confirmed: {iv.job_title} | NU10", confirmation_html(iv, iv.candidate_name, True))
    except Exception as e: errors.append("Candidate confirmation: " + str(e))
    try:
        send_email(iv.interviewer_email, f"Interview scheduled: {iv.candidate_name} | NU10", confirmation_html(iv, iv.interviewer_name, False))
    except Exception as e: errors.append("Interviewer confirmation: " + str(e))
    try:
        ta = os.getenv("TA_NOTIFICATION_EMAIL", "").strip()
        if ta:
            send_email(ta, f"Interview booked: {iv.candidate_name}", notify_ta_html(iv, "Interview booked", "The candidate selected an interview slot."))
    except Exception as e: errors.append("TA notification: " + str(e))
    iv.confirmation_sent = len(errors) == 0
    iv.status = "Interview scheduled" if not errors else "Scheduled - confirmation email issue"
    iv.last_error = "; ".join(errors)[:1000]
    db.commit()
    return HTMLResponse(f"""<!doctype html><html><body style="font-family:Arial;background:#f3f6fb;padding:32px"><main style="max-width:600px;margin:auto;background:white;padding:32px;border-radius:14px"><img src="{base_url()}/static/nu10logo.jpg" style="width:150px"><h1>Interview confirmed</h1><p>Thank you, {iv.candidate_name}. Your interview for <b>{iv.job_title}</b> is scheduled.</p><p><b>When:</b> {fmt_slot(iv.selected_slot)}</p><p><b>Meeting link:</b> <a href="{iv.meeting_url}">Join interview</a></p><p>Confirmation emails {'have been sent' if not errors else 'may not all have been delivered; the team will follow up'}.</p></main></body></html>""")

@app.get("/api/interviews")
def list_interviews(db=Depends(get_db)):
    rows = db.query(Interview).order_by(Interview.created_at.desc()).all()
    return [public_view(x) for x in rows]

@app.get("/api/interviews/{interview_id}")
def get_interview(interview_id: int, db=Depends(get_db)):
    iv = db.query(Interview).filter_by(id=interview_id).first()
    if not iv: raise HTTPException(404, "Interview not found.")
    return public_view(iv)

@app.post("/api/interviews/{interview_id}/resend")
def resend_invitation(interview_id: int, db=Depends(get_db)):
    iv = db.query(Interview).filter_by(id=interview_id).first()
    if not iv: raise HTTPException(404, "Interview not found.")
    if iv.selected_slot: raise HTTPException(400, "This interview is already scheduled.")
    try:
        send_email(iv.candidate_email, f"Interview invitation: {iv.job_title} | NU10", invitation_html(iv))
        iv.invitation_sent = True; iv.status = "Awaiting candidate selection"; iv.last_error = ""
    except Exception as e:
        iv.status = "Email failed"; iv.last_error = str(e)[:1000]
        db.commit()
        raise HTTPException(502, str(e))
    db.commit()
    return {"ok": True, "message": "Invitation resent."}


async def reminder_scan():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.query(Interview).filter(
            Interview.selected_slot.isnot(None)
        ).all()

        for iv in rows:
            try:
                dt = datetime.fromisoformat(
                    iv.selected_slot.replace("Z", "+00:00")
                )
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                delta = (
                    dt.astimezone(timezone.utc) - now
                ).total_seconds()

                if delta <= 0:
                    continue

                reminders = [
                    (24 * 3600, "reminder_24_sent", "24-hour"),
                    (3600, "reminder_1_sent", "1-hour"),
                    (15 * 60, "reminder_15_sent", "15-minute"),
                ]

                for seconds, field, label in reminders:
                    if getattr(iv, field):
                        continue

                    # Allow a 10-minute window after each reminder threshold.
                    if seconds - 600 < delta <= seconds:
                        content = email_shell(
                            f"<h2>{label} interview reminder</h2>"
                            f"<p>Hello,</p>"
                            f"<p>This is a reminder that the interview for "
                            f"<b>{iv.candidate_name}</b> ({iv.job_title}) "
                            f"is scheduled for "
                            f"<b>{fmt_slot(iv.selected_slot)}</b>.</p>"
                            f"<p><a href='{iv.meeting_url}'>"
                            f"Join interview meeting</a></p>"
                            f"<p>NU10 Talent Acquisition</p>"
                        )

                        # Mark as sent only after both email requests succeed.
                        send_email(
                            iv.candidate_email,
                            f"Reminder: {label} before your NU10 interview",
                            content,
                        )
                        send_email(
                            iv.interviewer_email,
                            f"Reminder: {label} before interview with "
                            f"{iv.candidate_name}",
                            content,
                        )

                        setattr(iv, field, True)
                        db.commit()
                        print(
                            f"REMINDER SENT: {label} | "
                            f"Interview ID: {iv.id}"
                        )

            except Exception as e:
                iv.last_error = (
                    (iv.last_error or "")
                    + f"\nReminder error: {str(e)}"
                )[-1000:]
                db.commit()
                print(
                    f"REMINDER FAILED for interview {iv.id}: {e}"
                )

    except Exception as e:
        print(f"REMINDER SCAN FAILED: {e}")
    finally:
        db.close()

