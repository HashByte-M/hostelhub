"""
HostelHub Backend — FastAPI + Neon PostgreSQL + Socket.IO
RGIPT Hostel Management System — Enhanced Version
Run: uvicorn main:socket_app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import os
import random
import string
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import socketio
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel, EmailStr

try:
    import aiosmtplib
    from email.mime.text import MIMEText
    SMTP_AVAILABLE = True
except ImportError:
    SMTP_AVAILABLE = False

load_dotenv()

# ─── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY   = os.environ.get("SECRET_KEY", "change-me-in-production-use-a-long-random-string")
ALGORITHM    = "HS256"
TOKEN_EXPIRE_HOURS = 24

SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))

OTP_EXPIRE_MINUTES = 10

# ─── Roles & Permissions ───────────────────────────────────────────────────────
VALID_ROLES = {
    "student", "hostel_rep", "mess_secretary", "maint_secretary",
    "warden", "head_warden", "super_admin"
}
ADMIN_ROLES = {
    "hostel_rep", "mess_secretary", "maint_secretary",
    "warden", "head_warden", "super_admin"
}
# Roles that can manage fines, items, rooms, visitors
WARDEN_ROLES = {"warden", "head_warden", "super_admin"}
# Roles that can post to ANY block (cross-block)
CROSS_BLOCK_ROLES = {"warden", "head_warden", "super_admin"}
# Roles that can manage complaints
MAINT_ROLES = {"maint_secretary", "warden", "head_warden", "super_admin"}

ALLOWED_DOMAIN = "rgipt.ac.in"

# ─── Hostel Structure ──────────────────────────────────────────────────────────
HOSTELS = [
    "asima_chatterjee", "a_block",
    "b_block", "c_block", "d_block", "e_block",
    "f_block", "g_block", "h_block"
]
HOSTEL_NAMES = {
    "asima_chatterjee": "Asima Chatterjee Hostel (Girls)",
    "a_block": "A Block (Girls)",
    "b_block": "B Block (Boys)",
    "c_block": "C Block (Boys)",
    "d_block": "D Block (Boys)",
    "e_block": "E Block (Boys)",
    "f_block": "F Block (Boys)",
    "g_block": "G Block (Boys)",
    "h_block": "H Block (Boys)",
    "all": "All Hostels"
}

# ─── Razorpay config ───────────────────────────────────────────────────────────
RAZORPAY_KEY_ID     = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_CURRENCY   = "INR"

# ─── Crypto ────────────────────────────────────────────────────────────────────
def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ─── In-memory OTP store ───────────────────────────────────────────────────────
_otp_store: Dict[str, tuple] = {}

# ─── Socket.IO ─────────────────────────────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

# ─── DB pool ───────────────────────────────────────────────────────────────────
_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    return _pool

# ─── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, statement_cache_size=0)
    await _init_db(_pool)
    yield
    await _pool.close()

async def _init_db(pool: asyncpg.Pool):
    """Create / migrate tables."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name    TEXT NOT NULL,
                last_name     TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'student',
                hostel        TEXT,
                roll_number   TEXT,
                phone         TEXT,
                is_approved   BOOLEAN NOT NULL DEFAULT FALSE,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS announcements (
                id          SERIAL PRIMARY KEY,
                author_id   INT REFERENCES users(id) ON DELETE SET NULL,
                title       TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'notice',
                tag         TEXT NOT NULL DEFAULT '',
                body        TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS notice_posts (
                id            SERIAL PRIMARY KEY,
                author_id     INT REFERENCES users(id) ON DELETE SET NULL,
                title         TEXT NOT NULL,
                body          TEXT NOT NULL,
                category      TEXT NOT NULL DEFAULT 'general',
                tag           TEXT NOT NULL DEFAULT '',
                target_blocks TEXT[] NOT NULL DEFAULT '{}',
                attachments   JSONB NOT NULL DEFAULT '[]',
                created_at    TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS meal_menu (
                id      SERIAL PRIMARY KEY,
                day     TEXT NOT NULL,
                meal    TEXT NOT NULL,
                items   TEXT[] NOT NULL DEFAULT '{}',
                UNIQUE (day, meal)
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id          SERIAL PRIMARY KEY,
                student_id  INT REFERENCES users(id) ON DELETE SET NULL,
                hostel      TEXT,
                location    TEXT NOT NULL,
                description TEXT NOT NULL,
                category    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'Open',
                assigned_to INT REFERENCES users(id) ON DELETE SET NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id          SERIAL PRIMARY KEY,
                user_id     INT REFERENCES users(id) ON DELETE SET NULL,
                area        TEXT NOT NULL,
                rating      INT NOT NULL,
                comments    TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS fines (
                id                  SERIAL PRIMARY KEY,
                student_id          INT REFERENCES users(id) ON DELETE SET NULL,
                amount              NUMERIC(10,2) NOT NULL,
                reason              TEXT NOT NULL,
                fine_type           TEXT NOT NULL DEFAULT 'general',
                issued_by           INT REFERENCES users(id) ON DELETE SET NULL,
                issued_at           TIMESTAMPTZ DEFAULT NOW(),
                due_date            DATE,
                status              TEXT NOT NULL DEFAULT 'unpaid',
                payment_method      TEXT,
                payment_reference   TEXT,
                razorpay_order_id   TEXT,
                linked_complaint_id INT REFERENCES complaints(id) ON DELETE SET NULL,
                linked_item_id      INT,
                notes               TEXT
            );

            CREATE TABLE IF NOT EXISTS prohibited_items (
                id               SERIAL PRIMARY KEY,
                student_id       INT REFERENCES users(id) ON DELETE SET NULL,
                room_number      TEXT NOT NULL,
                item_name        TEXT NOT NULL,
                item_description TEXT,
                quantity         INT NOT NULL DEFAULT 1,
                seized_by        INT REFERENCES users(id) ON DELETE SET NULL,
                seized_at        TIMESTAMPTZ DEFAULT NOW(),
                status           TEXT NOT NULL DEFAULT 'seized',
                return_date      TIMESTAMPTZ,
                disposal_notes   TEXT,
                linked_fine_id   INT REFERENCES fines(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS gatepass_requests (
                id                SERIAL PRIMARY KEY,
                student_id        INT REFERENCES users(id) ON DELETE SET NULL,
                hostel            TEXT NOT NULL,
                purpose           TEXT NOT NULL,
                destination       TEXT NOT NULL,
                departure_date    TIMESTAMPTZ NOT NULL,
                return_date       TIMESTAMPTZ NOT NULL,
                emergency_contact TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                approved_by       INT REFERENCES users(id) ON DELETE SET NULL,
                approved_at       TIMESTAMPTZ,
                rejection_reason  TEXT,
                created_at        TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS leave_requests (
                id              SERIAL PRIMARY KEY,
                student_id      INT REFERENCES users(id) ON DELETE SET NULL,
                hostel          TEXT NOT NULL,
                leave_type      TEXT NOT NULL DEFAULT 'home',
                reason          TEXT NOT NULL,
                from_date       DATE NOT NULL,
                to_date         DATE NOT NULL,
                parent_contact  TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                approved_by     INT REFERENCES users(id) ON DELETE SET NULL,
                approved_at     TIMESTAMPTZ,
                notes           TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS visitor_log (
                id           SERIAL PRIMARY KEY,
                student_id   INT REFERENCES users(id) ON DELETE SET NULL,
                hostel       TEXT NOT NULL,
                visitor_name TEXT NOT NULL,
                relation     TEXT NOT NULL,
                contact      TEXT NOT NULL,
                purpose      TEXT NOT NULL,
                entry_time   TIMESTAMPTZ DEFAULT NOW(),
                exit_time    TIMESTAMPTZ,
                logged_by    INT REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS room_allocations (
                id           SERIAL PRIMARY KEY,
                student_id   INT REFERENCES users(id) ON DELETE CASCADE,
                hostel       TEXT NOT NULL,
                room_number  TEXT NOT NULL,
                bed_number   TEXT,
                allocated_by INT REFERENCES users(id) ON DELETE SET NULL,
                allocated_at TIMESTAMPTZ DEFAULT NOW(),
                valid_until  DATE,
                UNIQUE(student_id)
            );
        """)

        # Migrate existing tables: add new columns if they don't exist
        migrate_queries = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hostel TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS roll_number TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
            "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS hostel TEXT",
            "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS assigned_to INT REFERENCES users(id) ON DELETE SET NULL",
        ]
        for q in migrate_queries:
            try:
                await conn.execute(q)
            except Exception:
                pass

        count = await conn.fetchval("SELECT COUNT(*) FROM meal_menu")
        if count == 0:
            await _seed_menu(conn)

async def _seed_menu(conn):
    default_menu = {
        "monday":    {"breakfast": ["Omelette","Toast","Milk","Banana"],      "lunch": ["Rajma","Rice","Roti","Salad"],            "snacks": ["Samosa","Chai"],               "dinner": ["Chicken Curry","Roti","Rice","Gulab Jamun"]},
        "tuesday":   {"breakfast": ["Poha","Jalebi","Tea"],                   "lunch": ["Chole","Bhature","Lassi"],                "snacks": ["Vegetable Sandwich","Coffee"],  "dinner": ["Paneer Butter Masala","Naan","Rice"]},
        "wednesday": {"breakfast": ["Idli","Sambar","Chutney"],               "lunch": ["Vegetable Pulao","Raita","Papad"],        "snacks": ["Bread Pakora","Chai"],          "dinner": ["Aloo Gobi","Dal Makhani","Roti","Rice"]},
        "thursday":  {"breakfast": ["Aloo Paratha","Curd","Pickle"],          "lunch": ["Kadhi Pakora","Rice","Roti"],             "snacks": ["Maggi","Tea"],                  "dinner": ["Egg Curry","Roti","Rice"]},
        "friday":    {"breakfast": ["Masala Dosa","Sambar"],                  "lunch": ["Fried Rice","Manchurian"],               "snacks": ["Biscuits","Milkshake"],         "dinner": ["Pav Bhaji","Fruit Salad"]},
        "saturday":  {"breakfast": ["Puri","Aloo Sabzi","Halwa"],             "lunch": ["South Indian Thali"],                    "snacks": ["Kachori","Chai"],               "dinner": ["Special Dinner: Biryani","Raita","Ice Cream"]},
        "sunday":    {"breakfast": ["Pancakes","Syrup","Fruits"],             "lunch": ["Dal Baati","Churma"],                    "snacks": ["Popcorn","Juice"],              "dinner": ["Masala Khichdi","Curd","Papad"]},
    }
    rows = [(day, meal, items) for day, meals in default_menu.items() for meal, items in meals.items()]
    await conn.executemany(
        "INSERT INTO meal_menu (day, meal, items) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", rows
    )

# ─── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="HostelHub API — RGIPT", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

# ─── JWT helpers ───────────────────────────────────────────────────────────────
def _create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), pool: asyncpg.Pool = Depends(get_pool)):
    cred_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise cred_exc
    except JWTError:
        raise cred_exc
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", int(user_id))
    if row is None:
        raise cred_exc
    return dict(row)

def require_role(*roles: str):
    async def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker

# ─── Pydantic models ───────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    role: str = "student"
    hostel: Optional[str] = None
    roll_number: Optional[str] = None
    phone: Optional[str] = None

class OtpSendRequest(BaseModel):
    email: str

class OtpVerifyRequest(BaseModel):
    email: str
    otp: str

class ForgotPasswordRequest(BaseModel):
    email: str

class AnnouncementCreate(BaseModel):
    title: str
    category: str
    tag: str = ""
    body: str

class NoticePostCreate(BaseModel):
    title: str
    body: str
    category: str = "general"
    tag: str = ""
    target_blocks: List[str] = []
    attachments: List[dict] = []  # [{name, type, size, data_base64}]

class MenuUpdateRequest(BaseModel):
    items: List[str]

class ComplaintCreate(BaseModel):
    location: str
    description: str
    category: str
    hostel: Optional[str] = None

class ComplaintStatusUpdate(BaseModel):
    status: str
    assigned_to: Optional[int] = None

class FeedbackCreate(BaseModel):
    area: str
    rating: int
    comments: str = ""

class ProfileUpdate(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    hostel: Optional[str] = None
    roll_number: Optional[str] = None

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str

class FineCreate(BaseModel):
    student_id: int
    amount: float
    reason: str
    fine_type: str = "general"
    due_date: Optional[str] = None
    linked_complaint_id: Optional[int] = None
    notes: Optional[str] = None

class FineStatusUpdate(BaseModel):
    status: str
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    notes: Optional[str] = None

class RazorpayVerifyRequest(BaseModel):
    fine_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class ProhibitedItemCreate(BaseModel):
    student_id: int
    room_number: str
    item_name: str
    item_description: Optional[str] = None
    quantity: int = 1
    linked_fine_id: Optional[int] = None

class ProhibitedItemStatusUpdate(BaseModel):
    status: str
    disposal_notes: Optional[str] = None

class GatepassCreate(BaseModel):
    hostel: str
    purpose: str
    destination: str
    departure_date: str
    return_date: str
    emergency_contact: str

class GatepassStatusUpdate(BaseModel):
    status: str  # approved | rejected
    rejection_reason: Optional[str] = None

class LeaveRequestCreate(BaseModel):
    hostel: str
    leave_type: str = "home"
    reason: str
    from_date: str
    to_date: str
    parent_contact: str

class LeaveStatusUpdate(BaseModel):
    status: str  # approved | rejected
    notes: Optional[str] = None

class VisitorLogCreate(BaseModel):
    student_id: int
    hostel: str
    visitor_name: str
    relation: str
    contact: str
    purpose: str

class RoomAllocationCreate(BaseModel):
    student_id: int
    hostel: str
    room_number: str
    bed_number: Optional[str] = None
    valid_until: Optional[str] = None

class RoleUpdateRequest(BaseModel):
    role: str
    hostel: Optional[str] = None

class HostelUpdateRequest(BaseModel):
    hostel: Optional[str] = None

# ─── Serializers ───────────────────────────────────────────────────────────────
def _fmt_date(dt) -> str:
    if not dt: return ""
    if isinstance(dt, datetime): return dt.strftime("%b %d, %Y")
    return str(dt)

def _fmt_datetime(dt) -> str:
    if not dt: return ""
    if isinstance(dt, datetime): return dt.strftime("%b %d, %Y %H:%M")
    return str(dt)

def _user_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "firstName": row["first_name"],
        "lastName": row["last_name"],
        "role": row["role"],
        "hostel": row.get("hostel"),
        "rollNumber": row.get("roll_number"),
        "phone": row.get("phone"),
        "isApproved": row["is_approved"],
        "createdAt": _fmt_date(row.get("created_at")),
    }

def _ann_out(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "tag": row["tag"] or "",
        "body": row["body"],
        "date": _fmt_date(row["created_at"]),
    }

def _notice_out(row) -> dict:
    attachments = row.get("attachments")
    if isinstance(attachments, str):
        try: attachments = json.loads(attachments)
        except: attachments = []
    elif attachments is None:
        attachments = []
    return {
        "id": row["id"],
        "authorId": row["author_id"],
        "authorName": row.get("author_name", "Unknown"),
        "authorRole": row.get("author_role", ""),
        "authorHostel": row.get("author_hostel"),
        "title": row["title"],
        "body": row["body"],
        "category": row["category"],
        "tag": row["tag"] or "",
        "targetBlocks": list(row["target_blocks"]) if row.get("target_blocks") else [],
        "attachments": attachments,
        "date": _fmt_datetime(row["created_at"]),
    }

def _complaint_out(row) -> dict:
    return {
        "id": row["id"],
        "location": row["location"],
        "description": row["description"],
        "category": row["category"],
        "hostel": row.get("hostel"),
        "status": row["status"],
        "date": _fmt_date(row["created_at"]),
    }

def _fine_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "amount": float(row["amount"]),
        "reason": row["reason"],
        "fineType": row["fine_type"],
        "issuedBy": row["issued_by"],
        "issuedAt": _fmt_date(row["issued_at"]),
        "dueDate": str(row["due_date"]) if row.get("due_date") else None,
        "status": row["status"],
        "paymentMethod": row.get("payment_method"),
        "paymentReference": row.get("payment_reference"),
        "razorpayOrderId": row.get("razorpay_order_id"),
        "linkedComplaintId": row.get("linked_complaint_id"),
        "linkedItemId": row.get("linked_item_id"),
        "notes": row.get("notes"),
    }

def _item_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "roomNumber": row["room_number"],
        "itemName": row["item_name"],
        "itemDescription": row.get("item_description"),
        "quantity": row["quantity"],
        "seizedBy": row["seized_by"],
        "seizedAt": _fmt_date(row["seized_at"]),
        "status": row["status"],
        "returnDate": _fmt_date(row["return_date"]) if row.get("return_date") else None,
        "disposalNotes": row.get("disposal_notes"),
        "linkedFineId": row.get("linked_fine_id"),
    }

def _gatepass_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "studentName": row.get("student_name"),
        "hostel": row["hostel"],
        "purpose": row["purpose"],
        "destination": row["destination"],
        "departureDate": _fmt_datetime(row["departure_date"]),
        "returnDate": _fmt_datetime(row["return_date"]),
        "emergencyContact": row["emergency_contact"],
        "status": row["status"],
        "approvedBy": row.get("approved_by"),
        "approvedAt": _fmt_datetime(row.get("approved_at")),
        "rejectionReason": row.get("rejection_reason"),
        "createdAt": _fmt_datetime(row["created_at"]),
    }

def _leave_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "studentName": row.get("student_name"),
        "hostel": row["hostel"],
        "leaveType": row["leave_type"],
        "reason": row["reason"],
        "fromDate": str(row["from_date"]),
        "toDate": str(row["to_date"]),
        "parentContact": row["parent_contact"],
        "status": row["status"],
        "approvedBy": row.get("approved_by"),
        "approvedAt": _fmt_datetime(row.get("approved_at")),
        "notes": row.get("notes"),
        "createdAt": _fmt_datetime(row["created_at"]),
    }

def _visitor_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "studentName": row.get("student_name"),
        "hostel": row["hostel"],
        "visitorName": row["visitor_name"],
        "relation": row["relation"],
        "contact": row["contact"],
        "purpose": row["purpose"],
        "entryTime": _fmt_datetime(row["entry_time"]),
        "exitTime": _fmt_datetime(row.get("exit_time")) if row.get("exit_time") else None,
        "loggedBy": row.get("logged_by"),
    }

def _room_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "studentName": row.get("student_name"),
        "studentEmail": row.get("student_email"),
        "hostel": row["hostel"],
        "roomNumber": row["room_number"],
        "bedNumber": row.get("bed_number"),
        "allocatedBy": row.get("allocated_by"),
        "allocatedAt": _fmt_datetime(row["allocated_at"]),
        "validUntil": str(row["valid_until"]) if row.get("valid_until") else None,
    }

# ─── Auth routes ───────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def login(body: LoginRequest, pool: asyncpg.Pool = Depends(get_pool)):
    row = await pool.fetchrow("SELECT * FROM users WHERE email = $1", body.email.lower())
    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not row["is_approved"]:
        raise HTTPException(status_code=403, detail="Your account is pending approval by a Super Admin.")
    token = _create_token({"sub": str(row["id"])})
    return {"token": token, "user": _user_out(dict(row))}


async def _send_otp_email(to_email: str, otp: str):
    if not SMTP_AVAILABLE or not SMTP_EMAIL or not SMTP_PASSWORD:
        print(f"[OTP] {to_email} → {otp}  (configure SMTP to send real emails)")
        return
    msg = MIMEText(f"""Your RGIPT HostelHub verification code is: {otp}\n\nExpires in {OTP_EXPIRE_MINUTES} minutes.\n— HostelHub, RGIPT""")
    msg["Subject"] = "HostelHub OTP — RGIPT"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    try:
        await aiosmtplib.send(msg, hostname=SMTP_HOST, port=SMTP_PORT, username=SMTP_EMAIL, password=SMTP_PASSWORD, start_tls=True)
    except Exception as e:
        print(f"[OTP] Email failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP. Try again.")


@app.post("/auth/send-otp")
async def send_otp(body: OtpSendRequest, pool: asyncpg.Pool = Depends(get_pool)):
    if not body.email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        raise HTTPException(status_code=400, detail=f"Only @{ALLOWED_DOMAIN} email addresses are allowed.")
    existing = await pool.fetchval("SELECT id FROM users WHERE email = $1", body.email.lower())
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    otp = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)
    _otp_store[body.email.lower()] = (otp, expires_at)
    await _send_otp_email(body.email.lower(), otp)
    response: dict = {"success": True}
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        response["dev_otp"] = otp
    return response


@app.post("/auth/verify-otp")
async def verify_otp(body: OtpVerifyRequest):
    entry = _otp_store.get(body.email.lower())
    if not entry:
        raise HTTPException(status_code=400, detail="OTP not found. Please request a new one.")
    stored_otp, expires_at = entry
    if datetime.now(timezone.utc) > expires_at:
        del _otp_store[body.email.lower()]
        raise HTTPException(status_code=400, detail="OTP has expired.")
    if stored_otp != body.otp.strip():
        raise HTTPException(status_code=400, detail="Invalid OTP.")
    _otp_store[body.email.lower()] = ("verified:" + stored_otp, expires_at)
    return {"success": True}


@app.post("/auth/register")
async def register(body: RegisterRequest, pool: asyncpg.Pool = Depends(get_pool)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role.")
    if body.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin accounts can only be assigned by an existing Super Admin.")
    if not body.email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        raise HTTPException(status_code=400, detail=f"Only @{ALLOWED_DOMAIN} email addresses are allowed.")
    entry = _otp_store.get(body.email.lower())
    if not entry or not entry[0].startswith("verified:"):
        raise HTTPException(status_code=400, detail="Email not verified. Please complete OTP verification first.")
    is_approved = body.role == "student"
    hashed = _hash_password(body.password)
    try:
        row = await pool.fetchrow(
            """INSERT INTO users (email, password_hash, first_name, last_name, role, hostel, roll_number, phone, is_approved)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
            body.email.lower(), hashed, body.first_name, body.last_name, body.role,
            body.hostel, body.roll_number, body.phone, is_approved
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    _otp_store.pop(body.email.lower(), None)
    return {"user": _user_out(dict(row)), "requiresApproval": not is_approved}


@app.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, pool: asyncpg.Pool = Depends(get_pool)):
    row = await pool.fetchrow("SELECT id FROM users WHERE email = $1", body.email.lower())
    if row:
        print(f"[PASSWORD RESET] Reset requested for {body.email}")
    return {"success": True}


# ─── Announcements (legacy) ─────────────────────────────────────────────────────
@app.get("/announcements")
async def get_announcements(pool: asyncpg.Pool = Depends(get_pool), _=Depends(get_current_user)):
    rows = await pool.fetch("SELECT * FROM announcements ORDER BY created_at DESC")
    return [_ann_out(r) for r in rows]


@app.post("/announcements")
async def post_announcement(
    body: AnnouncementCreate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("hostel_rep", "mess_secretary", "maint_secretary", "warden", "head_warden", "super_admin"))
):
    row = await pool.fetchrow(
        "INSERT INTO announcements (author_id, title, category, tag, body) VALUES ($1, $2, $3, $4, $5) RETURNING *",
        user["id"], body.title, body.category, body.tag, body.body
    )
    ann = _ann_out(dict(row))
    await sio.emit("new_announcement", ann)
    return ann


# ─── Notice Board (block-wise with attachments) ────────────────────────────────
@app.get("/notice-posts")
async def get_notice_posts(
    hostel: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(get_current_user)
):
    """Get notice posts. Students see posts for their hostel + all-hostel posts. Officials see all."""
    if user["role"] in CROSS_BLOCK_ROLES or user["role"] in ADMIN_ROLES:
        # Admins and officials see everything, optionally filtered by hostel
        if hostel:
            rows = await pool.fetch(
                """SELECT np.*, u.first_name || ' ' || u.last_name AS author_name,
                          u.role AS author_role, u.hostel AS author_hostel
                   FROM notice_posts np LEFT JOIN users u ON u.id = np.author_id
                   WHERE $1 = ANY(np.target_blocks) OR 'all' = ANY(np.target_blocks)
                   ORDER BY np.created_at DESC""",
                hostel
            )
        else:
            rows = await pool.fetch(
                """SELECT np.*, u.first_name || ' ' || u.last_name AS author_name,
                          u.role AS author_role, u.hostel AS author_hostel
                   FROM notice_posts np LEFT JOIN users u ON u.id = np.author_id
                   ORDER BY np.created_at DESC"""
            )
    else:
        # Students / hostel_rep / mess_secy / maint_secy see posts for their hostel
        user_hostel = user.get("hostel") or "all"
        rows = await pool.fetch(
            """SELECT np.*, u.first_name || ' ' || u.last_name AS author_name,
                      u.role AS author_role, u.hostel AS author_hostel
               FROM notice_posts np LEFT JOIN users u ON u.id = np.author_id
               WHERE $1 = ANY(np.target_blocks) OR 'all' = ANY(np.target_blocks)
               ORDER BY np.created_at DESC""",
            user_hostel
        )
    return [_notice_out(dict(r)) for r in rows]


@app.post("/notice-posts", status_code=201)
async def create_notice_post(
    body: NoticePostCreate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("hostel_rep", "mess_secretary", "maint_secretary", "warden", "head_warden", "super_admin"))
):
    """Post a notice. Cross-block posting restricted to warden+, head_warden, super_admin."""
    user_hostel = user.get("hostel") or "all"
    
    # Validate target blocks
    for block in body.target_blocks:
        if block != "all" and block not in HOSTELS:
            raise HTTPException(status_code=400, detail=f"Invalid hostel block: {block}")
    
    # Check cross-block permissions
    if user["role"] not in CROSS_BLOCK_ROLES:
        # hostel_rep, mess_secretary, maint_secretary can only post to their own hostel
        for block in body.target_blocks:
            if block != user_hostel and block != "all":
                raise HTTPException(
                    status_code=403,
                    detail=f"You can only post notices to your own hostel ({user_hostel}). Cross-block posting requires Warden or Head Warden role."
                )
        # Force target to own hostel if not set
        if not body.target_blocks:
            body.target_blocks = [user_hostel]
    
    # Super admins / head wardens can post to 'all'
    if not body.target_blocks:
        body.target_blocks = [user_hostel if user_hostel else "all"]

    row = await pool.fetchrow(
        """INSERT INTO notice_posts (author_id, title, body, category, tag, target_blocks, attachments)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
        user["id"], body.title, body.body, body.category, body.tag,
        body.target_blocks, json.dumps(body.attachments)
    )
    # Fetch with author info
    full = await pool.fetchrow(
        """SELECT np.*, u.first_name || ' ' || u.last_name AS author_name,
                  u.role AS author_role, u.hostel AS author_hostel
           FROM notice_posts np LEFT JOIN users u ON u.id = np.author_id
           WHERE np.id = $1""",
        row["id"]
    )
    notice = _notice_out(dict(full))
    await sio.emit("new_notice_post", notice)
    return notice


@app.delete("/notice-posts/{post_id}")
async def delete_notice_post(
    post_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("warden", "head_warden", "super_admin", "hostel_rep", "mess_secretary", "maint_secretary"))
):
    row = await pool.fetchrow("SELECT * FROM notice_posts WHERE id = $1", post_id)
    if not row:
        raise HTTPException(status_code=404, detail="Notice not found.")
    # Only author or super_admin / head_warden can delete
    if row["author_id"] != user["id"] and user["role"] not in {"super_admin", "head_warden"}:
        raise HTTPException(status_code=403, detail="You can only delete your own notices.")
    await pool.execute("DELETE FROM notice_posts WHERE id = $1", post_id)
    await sio.emit("notice_post_deleted", {"id": post_id})
    return {"success": True}


# ─── Menu ──────────────────────────────────────────────────────────────────────
@app.get("/menu/{day}")
async def get_menu(day: str, pool: asyncpg.Pool = Depends(get_pool), _=Depends(get_current_user)):
    rows = await pool.fetch("SELECT meal, items FROM meal_menu WHERE day = $1", day.lower())
    if not rows:
        raise HTTPException(status_code=404, detail="Menu not found.")
    return {r["meal"]: list(r["items"]) for r in rows}


@app.put("/menu/{day}/{meal}")
async def update_menu(
    day: str, meal: str,
    body: MenuUpdateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("mess_secretary", "warden", "head_warden", "super_admin"))
):
    await pool.execute(
        "UPDATE meal_menu SET items = $1 WHERE day = $2 AND meal = $3",
        body.items, day.lower(), meal.lower()
    )
    payload = {"day": day.lower(), "meal": meal.lower(), "items": body.items}
    await sio.emit("menu_updated", payload)
    return {"success": True}


# ─── Complaints ────────────────────────────────────────────────────────────────
@app.get("/complaints")
async def get_complaints(pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if user["role"] in ADMIN_ROLES:
        rows = await pool.fetch("SELECT * FROM complaints ORDER BY created_at DESC")
    else:
        rows = await pool.fetch(
            "SELECT * FROM complaints WHERE student_id = $1 ORDER BY created_at DESC", user["id"]
        )
    return [_complaint_out(r) for r in rows]


@app.post("/complaints")
async def post_complaint(body: ComplaintCreate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    hostel = body.hostel or user.get("hostel")
    row = await pool.fetchrow(
        "INSERT INTO complaints (student_id, hostel, location, description, category) VALUES ($1, $2, $3, $4, $5) RETURNING *",
        user["id"], hostel, body.location, body.description, body.category
    )
    complaint = _complaint_out(dict(row))
    await sio.emit("new_complaint", complaint)
    return complaint


@app.patch("/complaints/{complaint_id}")
async def update_complaint_status(
    complaint_id: int,
    body: ComplaintStatusUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("maint_secretary", "warden", "head_warden", "super_admin"))
):
    valid = {"Open", "In Progress", "Resolved"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid}")
    row = await pool.fetchrow(
        "UPDATE complaints SET status = $1 WHERE id = $2 RETURNING *", body.status, complaint_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Complaint not found.")
    complaint = _complaint_out(dict(row))
    await sio.emit("complaint_status_updated", complaint)
    return complaint


@app.patch("/complaints/{complaint_id}/resolve")
async def student_resolve_complaint(complaint_id: int, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    row = await pool.fetchrow(
        "UPDATE complaints SET status = 'Resolved' WHERE id = $1 AND student_id = $2 RETURNING *",
        complaint_id, user["id"]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Complaint not found or permission denied.")
    complaint = _complaint_out(dict(row))
    await sio.emit("complaint_status_updated", complaint)
    return complaint


# ─── Feedback ──────────────────────────────────────────────────────────────────
@app.post("/feedback")
async def post_feedback(body: FeedbackCreate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    await pool.execute(
        "INSERT INTO feedback (user_id, area, rating, comments) VALUES ($1, $2, $3, $4)",
        user["id"], body.area, body.rating, body.comments
    )
    return {"success": True}


# ─── Profile ───────────────────────────────────────────────────────────────────
@app.put("/users/me")
async def update_profile(body: ProfileUpdate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    row = await pool.fetchrow(
        "UPDATE users SET first_name=$1, last_name=$2, phone=$3, hostel=$4, roll_number=$5 WHERE id=$6 RETURNING *",
        body.first_name, body.last_name, body.phone, body.hostel, body.roll_number, user["id"]
    )
    return _user_out(dict(row))


@app.put("/users/me/password")
async def update_password(body: PasswordUpdate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user["id"])
    if not _verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    new_hash = _hash_password(body.new_password)
    await pool.execute("UPDATE users SET password_hash = $1 WHERE id = $2", new_hash, user["id"])
    return {"success": True}


# ─── Super Admin: User Management ─────────────────────────────────────────────
@app.get("/admin/users")
async def get_all_users(pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role("super_admin"))):
    rows = await pool.fetch("SELECT * FROM users ORDER BY created_at DESC")
    return [_user_out(dict(r)) for r in rows]

@app.get("/admin/users/pending")
async def get_pending_users(pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role("super_admin"))):
    rows = await pool.fetch("SELECT * FROM users WHERE is_approved = FALSE ORDER BY created_at DESC")
    return [_user_out(dict(r)) for r in rows]

@app.patch("/admin/users/{user_id}/approve")
async def approve_user(user_id: int, pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role("super_admin"))):
    row = await pool.fetchrow("UPDATE users SET is_approved = TRUE WHERE id = $1 RETURNING *", user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    await sio.emit("user_approved", _user_out(dict(row)))
    return {"success": True, "user": _user_out(dict(row))}

@app.delete("/admin/users/{user_id}/reject")
async def reject_user(user_id: int, pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role("super_admin"))):
    row = await pool.fetchrow("DELETE FROM users WHERE id = $1 AND is_approved = FALSE RETURNING id", user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found or already approved.")
    return {"success": True}

@app.patch("/admin/users/{user_id}/role")
async def change_user_role(
    user_id: int, body: RoleUpdateRequest,
    pool: asyncpg.Pool = Depends(get_pool), current_user=Depends(require_role("super_admin"))
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role.")
    if user_id == current_user["id"] and body.role != "super_admin":
        raise HTTPException(status_code=400, detail="You cannot demote yourself.")
    update_hostel = body.hostel if body.hostel else None
    row = await pool.fetchrow(
        "UPDATE users SET role=$1, is_approved=TRUE, hostel=COALESCE($2, hostel) WHERE id=$3 RETURNING *",
        body.role, update_hostel, user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"success": True, "user": _user_out(dict(row))}

@app.patch("/admin/users/{user_id}/hostel")
async def assign_hostel(
    user_id: int, body: HostelUpdateRequest,
    pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role("super_admin", "head_warden"))
):
    row = await pool.fetchrow("UPDATE users SET hostel=$1 WHERE id=$2 RETURNING *", body.hostel, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"success": True, "user": _user_out(dict(row))}

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, pool: asyncpg.Pool = Depends(get_pool), current_user=Depends(require_role("super_admin"))):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    row = await pool.fetchrow("DELETE FROM users WHERE id = $1 RETURNING id", user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"success": True}


# ─── Fines ─────────────────────────────────────────────────────────────────────
FINE_TYPES = {"general", "late_return", "damage", "disciplinary", "mess"}
FINE_STATUSES = {"unpaid", "paid", "waived", "disputed"}

@app.get("/fines")
async def get_fines(status: Optional[str] = None, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if user["role"] in WARDEN_ROLES:
        if status and status in FINE_STATUSES:
            rows = await pool.fetch("SELECT * FROM fines WHERE status=$1 ORDER BY issued_at DESC", status)
        else:
            rows = await pool.fetch("SELECT * FROM fines ORDER BY issued_at DESC")
    else:
        if status and status in FINE_STATUSES:
            rows = await pool.fetch(
                "SELECT * FROM fines WHERE student_id=$1 AND status=$2 ORDER BY issued_at DESC", user["id"], status
            )
        else:
            rows = await pool.fetch("SELECT * FROM fines WHERE student_id=$1 ORDER BY issued_at DESC", user["id"])
    return [_fine_out(dict(r)) for r in rows]


@app.get("/fines/summary/me")
async def get_my_fine_summary(pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    row = await pool.fetchrow(
        "SELECT COALESCE(SUM(amount), 0) AS total_unpaid FROM fines WHERE student_id=$1 AND status='unpaid'", user["id"]
    )
    return {"totalUnpaid": float(row["total_unpaid"])}


@app.post("/fines", status_code=201)
async def create_fine(body: FineCreate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(require_role(*WARDEN_ROLES))):
    if body.fine_type not in FINE_TYPES:
        raise HTTPException(status_code=400, detail=f"fine_type must be one of: {FINE_TYPES}")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")
    student = await pool.fetchrow("SELECT id FROM users WHERE id = $1", body.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    row = await pool.fetchrow(
        """INSERT INTO fines (student_id, amount, reason, fine_type, issued_by, due_date, linked_complaint_id, notes)
           VALUES ($1, $2, $3, $4, $5, $6::DATE, $7, $8) RETURNING *""",
        body.student_id, body.amount, body.reason, body.fine_type, user["id"],
        body.due_date, body.linked_complaint_id, body.notes
    )
    fine = _fine_out(dict(row))
    await sio.emit("new_fine", fine)
    return fine


@app.patch("/fines/{fine_id}/mark-paid-cash")
async def mark_fine_paid_cash(fine_id: int, body: FineStatusUpdate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(require_role(*WARDEN_ROLES))):
    row = await pool.fetchrow("SELECT * FROM fines WHERE id = $1", fine_id)
    if not row:
        raise HTTPException(status_code=404, detail="Fine not found.")
    if row["status"] == "paid":
        raise HTTPException(status_code=400, detail="Fine already paid.")
    updated = await pool.fetchrow(
        "UPDATE fines SET status='paid', payment_method='cash', payment_reference=$1, notes=COALESCE($2,notes) WHERE id=$3 RETURNING *",
        body.payment_reference, body.notes, fine_id
    )
    fine = _fine_out(dict(updated))
    await sio.emit("fine_updated", fine)
    return fine


@app.patch("/fines/{fine_id}/waive")
async def waive_fine(fine_id: int, body: FineStatusUpdate, pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role("super_admin"))):
    row = await pool.fetchrow("SELECT * FROM fines WHERE id = $1", fine_id)
    if not row:
        raise HTTPException(status_code=404, detail="Fine not found.")
    updated = await pool.fetchrow(
        "UPDATE fines SET status='waived', notes=COALESCE($1,notes) WHERE id=$2 RETURNING *", body.notes, fine_id
    )
    fine = _fine_out(dict(updated))
    await sio.emit("fine_updated", fine)
    return fine


# ─── Razorpay Scaffold ──────────────────────────────────────────────────────────
@app.post("/fines/{fine_id}/razorpay/create-order")
async def razorpay_create_order(fine_id: int, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=503, detail="Razorpay integration not yet activated.")
    return {"scaffold": True}

@app.post("/fines/{fine_id}/razorpay/verify")
async def razorpay_verify(fine_id: int, body: RazorpayVerifyRequest, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=503, detail="Razorpay integration not yet activated.")
    return {"scaffold": True}


# ─── Prohibited Items ───────────────────────────────────────────────────────────
PROHIBITED_STATUSES = {"seized", "returned", "disposed"}

@app.get("/prohibited-items")
async def get_prohibited_items(status: Optional[str] = None, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if user["role"] in WARDEN_ROLES:
        if status and status in PROHIBITED_STATUSES:
            rows = await pool.fetch("SELECT * FROM prohibited_items WHERE status=$1 ORDER BY seized_at DESC", status)
        else:
            rows = await pool.fetch("SELECT * FROM prohibited_items ORDER BY seized_at DESC")
    else:
        rows = await pool.fetch("SELECT * FROM prohibited_items WHERE student_id=$1 ORDER BY seized_at DESC", user["id"])
    return [_item_out(dict(r)) for r in rows]


@app.post("/prohibited-items", status_code=201)
async def log_prohibited_item(body: ProhibitedItemCreate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(require_role(*WARDEN_ROLES))):
    student = await pool.fetchrow("SELECT id FROM users WHERE id = $1", body.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    row = await pool.fetchrow(
        """INSERT INTO prohibited_items (student_id, room_number, item_name, item_description, quantity, seized_by, linked_fine_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
        body.student_id, body.room_number, body.item_name, body.item_description, body.quantity, user["id"], body.linked_fine_id
    )
    item = _item_out(dict(row))
    await sio.emit("new_prohibited_item", item)
    return item


@app.patch("/prohibited-items/{item_id}")
async def update_prohibited_item(item_id: int, body: ProhibitedItemStatusUpdate, pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role(*WARDEN_ROLES))):
    if body.status not in PROHIBITED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {PROHIBITED_STATUSES}")
    updated = await pool.fetchrow(
        """UPDATE prohibited_items SET status=$1,
           return_date=CASE WHEN $1='returned' THEN NOW() ELSE return_date END,
           disposal_notes=COALESCE($2,disposal_notes) WHERE id=$3 RETURNING *""",
        body.status, body.disposal_notes, item_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found.")
    item = _item_out(dict(updated))
    await sio.emit("prohibited_item_updated", item)
    return item


@app.patch("/prohibited-items/{item_id}/link-fine")
async def link_fine_to_item(item_id: int, fine_id: int, pool: asyncpg.Pool = Depends(get_pool), _=Depends(require_role(*WARDEN_ROLES))):
    fine = await pool.fetchrow("SELECT id FROM fines WHERE id = $1", fine_id)
    if not fine:
        raise HTTPException(status_code=404, detail="Fine not found.")
    row = await pool.fetchrow("UPDATE prohibited_items SET linked_fine_id=$1 WHERE id=$2 RETURNING *", fine_id, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found.")
    return _item_out(dict(row))


# ─── Gatepass Requests ──────────────────────────────────────────────────────────
@app.get("/gatepass")
async def get_gatepasses(
    hostel: Optional[str] = None,
    status: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(get_current_user)
):
    if user["role"] in ADMIN_ROLES:
        filters = []
        params = []
        if hostel:
            params.append(hostel)
            filters.append(f"gr.hostel = ${len(params)}")
        if status:
            params.append(status)
            filters.append(f"gr.status = ${len(params)}")
        where = "WHERE " + " AND ".join(filters) if filters else ""
        rows = await pool.fetch(
            f"""SELECT gr.*, u.first_name || ' ' || u.last_name AS student_name
                FROM gatepass_requests gr LEFT JOIN users u ON u.id = gr.student_id
                {where} ORDER BY gr.created_at DESC""",
            *params
        )
    else:
        rows = await pool.fetch(
            """SELECT gr.*, u.first_name || ' ' || u.last_name AS student_name
               FROM gatepass_requests gr LEFT JOIN users u ON u.id = gr.student_id
               WHERE gr.student_id = $1 ORDER BY gr.created_at DESC""",
            user["id"]
        )
    return [_gatepass_out(dict(r)) for r in rows]


@app.post("/gatepass", status_code=201)
async def create_gatepass(body: GatepassCreate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if body.hostel not in HOSTELS:
        raise HTTPException(status_code=400, detail="Invalid hostel.")
    row = await pool.fetchrow(
        """INSERT INTO gatepass_requests (student_id, hostel, purpose, destination, departure_date, return_date, emergency_contact)
           VALUES ($1,$2,$3,$4,$5::TIMESTAMPTZ,$6::TIMESTAMPTZ,$7) RETURNING *""",
        user["id"], body.hostel, body.purpose, body.destination,
        body.departure_date, body.return_date, body.emergency_contact
    )
    gp = _gatepass_out(dict(row))
    await sio.emit("new_gatepass", gp)
    return gp


@app.patch("/gatepass/{gp_id}")
async def update_gatepass(
    gp_id: int, body: GatepassStatusUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("hostel_rep", "warden", "head_warden", "super_admin"))
):
    if body.status not in {"approved", "rejected", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid status.")
    approved_at = "NOW()" if body.status == "approved" else None
    row = await pool.fetchrow(
        """UPDATE gatepass_requests SET status=$1, approved_by=$2,
           approved_at=CASE WHEN $1='approved' THEN NOW() ELSE approved_at END,
           rejection_reason=$3 WHERE id=$4 RETURNING *""",
        body.status, user["id"], body.rejection_reason, gp_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Gatepass not found.")
    gp = _gatepass_out(dict(row))
    await sio.emit("gatepass_updated", gp)
    return gp


# ─── Leave Requests ─────────────────────────────────────────────────────────────
@app.get("/leave")
async def get_leave_requests(
    hostel: Optional[str] = None,
    status: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(get_current_user)
):
    if user["role"] in ADMIN_ROLES:
        filters = []
        params = []
        if hostel:
            params.append(hostel)
            filters.append(f"lr.hostel = ${len(params)}")
        if status:
            params.append(status)
            filters.append(f"lr.status = ${len(params)}")
        where = "WHERE " + " AND ".join(filters) if filters else ""
        rows = await pool.fetch(
            f"""SELECT lr.*, u.first_name || ' ' || u.last_name AS student_name
                FROM leave_requests lr LEFT JOIN users u ON u.id = lr.student_id
                {where} ORDER BY lr.created_at DESC""",
            *params
        )
    else:
        rows = await pool.fetch(
            """SELECT lr.*, u.first_name || ' ' || u.last_name AS student_name
               FROM leave_requests lr LEFT JOIN users u ON u.id = lr.student_id
               WHERE lr.student_id = $1 ORDER BY lr.created_at DESC""",
            user["id"]
        )
    return [_leave_out(dict(r)) for r in rows]


@app.post("/leave", status_code=201)
async def create_leave(body: LeaveRequestCreate, pool: asyncpg.Pool = Depends(get_pool), user=Depends(get_current_user)):
    if body.hostel not in HOSTELS:
        raise HTTPException(status_code=400, detail="Invalid hostel.")
    row = await pool.fetchrow(
        """INSERT INTO leave_requests (student_id, hostel, leave_type, reason, from_date, to_date, parent_contact)
           VALUES ($1,$2,$3,$4,$5::DATE,$6::DATE,$7) RETURNING *""",
        user["id"], body.hostel, body.leave_type, body.reason,
        body.from_date, body.to_date, body.parent_contact
    )
    lr = _leave_out(dict(row))
    await sio.emit("new_leave_request", lr)
    return lr


@app.patch("/leave/{leave_id}")
async def update_leave(
    leave_id: int, body: LeaveStatusUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("warden", "head_warden", "super_admin"))
):
    if body.status not in {"approved", "rejected", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid status.")
    row = await pool.fetchrow(
        """UPDATE leave_requests SET status=$1, approved_by=$2,
           approved_at=CASE WHEN $1 IN ('approved','rejected') THEN NOW() ELSE approved_at END,
           notes=$3 WHERE id=$4 RETURNING *""",
        body.status, user["id"], body.notes, leave_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    lr = _leave_out(dict(row))
    await sio.emit("leave_updated", lr)
    return lr


# ─── Visitor Log ────────────────────────────────────────────────────────────────
@app.get("/visitors")
async def get_visitors(
    hostel: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("warden", "head_warden", "super_admin", "hostel_rep"))
):
    if hostel:
        rows = await pool.fetch(
            """SELECT vl.*, u.first_name || ' ' || u.last_name AS student_name
               FROM visitor_log vl LEFT JOIN users u ON u.id = vl.student_id
               WHERE vl.hostel = $1 ORDER BY vl.entry_time DESC""",
            hostel
        )
    else:
        rows = await pool.fetch(
            """SELECT vl.*, u.first_name || ' ' || u.last_name AS student_name
               FROM visitor_log vl LEFT JOIN users u ON u.id = vl.student_id
               ORDER BY vl.entry_time DESC"""
        )
    return [_visitor_out(dict(r)) for r in rows]


@app.post("/visitors", status_code=201)
async def log_visitor(
    body: VisitorLogCreate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("warden", "head_warden", "super_admin", "hostel_rep"))
):
    student = await pool.fetchrow("SELECT id FROM users WHERE id = $1", body.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    row = await pool.fetchrow(
        """INSERT INTO visitor_log (student_id, hostel, visitor_name, relation, contact, purpose, logged_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
        body.student_id, body.hostel, body.visitor_name, body.relation,
        body.contact, body.purpose, user["id"]
    )
    return _visitor_out(dict(row))


@app.patch("/visitors/{visitor_id}/exit")
async def log_visitor_exit(
    visitor_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    _=Depends(require_role("warden", "head_warden", "super_admin", "hostel_rep"))
):
    row = await pool.fetchrow(
        "UPDATE visitor_log SET exit_time = NOW() WHERE id = $1 RETURNING *", visitor_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Visitor record not found.")
    return _visitor_out(dict(row))


# ─── Room Management ────────────────────────────────────────────────────────────
@app.get("/rooms")
async def get_rooms(
    hostel: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("warden", "head_warden", "super_admin"))
):
    if hostel:
        rows = await pool.fetch(
            """SELECT ra.*, u.first_name || ' ' || u.last_name AS student_name, u.email AS student_email
               FROM room_allocations ra LEFT JOIN users u ON u.id = ra.student_id
               WHERE ra.hostel = $1 ORDER BY ra.room_number""",
            hostel
        )
    else:
        rows = await pool.fetch(
            """SELECT ra.*, u.first_name || ' ' || u.last_name AS student_name, u.email AS student_email
               FROM room_allocations ra LEFT JOIN users u ON u.id = ra.student_id
               ORDER BY ra.hostel, ra.room_number"""
        )
    return [_room_out(dict(r)) for r in rows]


@app.post("/rooms", status_code=201)
async def allocate_room(
    body: RoomAllocationCreate,
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role("warden", "head_warden", "super_admin"))
):
    student = await pool.fetchrow("SELECT id FROM users WHERE id = $1", body.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    try:
        row = await pool.fetchrow(
            """INSERT INTO room_allocations (student_id, hostel, room_number, bed_number, allocated_by, valid_until)
               VALUES ($1,$2,$3,$4,$5,$6::DATE) RETURNING *""",
            body.student_id, body.hostel, body.room_number, body.bed_number, user["id"], body.valid_until
        )
    except asyncpg.UniqueViolationError:
        # Update existing allocation
        row = await pool.fetchrow(
            """UPDATE room_allocations SET hostel=$1, room_number=$2, bed_number=$3, allocated_by=$4, valid_until=$5::DATE
               WHERE student_id=$6 RETURNING *""",
            body.hostel, body.room_number, body.bed_number, user["id"], body.valid_until, body.student_id
        )
    ra = _room_out(dict(row))
    await sio.emit("room_updated", ra)
    return ra


@app.delete("/rooms/{room_id}")
async def deallocate_room(
    room_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    _=Depends(require_role("warden", "head_warden", "super_admin"))
):
    row = await pool.fetchrow("DELETE FROM room_allocations WHERE id = $1 RETURNING id", room_id)
    if not row:
        raise HTTPException(status_code=404, detail="Allocation not found.")
    return {"success": True}


# ─── Hostel Info ────────────────────────────────────────────────────────────────
@app.get("/hostels")
async def get_hostels(_=Depends(get_current_user)):
    return [{"id": k, "name": v} for k, v in HOSTEL_NAMES.items()]


@app.get("/users/search")
async def search_users(
    q: str = "",
    pool: asyncpg.Pool = Depends(get_pool),
    user=Depends(require_role(*WARDEN_ROLES))
):
    """Search users by name or email for autocomplete (wardens only)."""
    if len(q) < 2:
        return []
    rows = await pool.fetch(
        """SELECT id, first_name, last_name, email, hostel, roll_number FROM users
           WHERE (first_name ILIKE $1 OR last_name ILIKE $1 OR email ILIKE $1)
           AND role = 'student' AND is_approved = TRUE
           LIMIT 20""",
        f"%{q}%"
    )
    return [{"id": r["id"], "name": f"{r['first_name']} {r['last_name']}", "email": r["email"], "hostel": r["hostel"], "rollNumber": r.get("roll_number")} for r in rows]


# ─── Socket.IO ─────────────────────────────────────────────────────────────────
@sio.event
async def connect(sid, environ, auth):
    token = (auth or {}).get("token")
    if not token:
        raise socketio.exceptions.ConnectionRefusedError("Authentication required")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise socketio.exceptions.ConnectionRefusedError("Invalid token")
        await sio.save_session(sid, {"user_id": user_id})
    except JWTError:
        raise socketio.exceptions.ConnectionRefusedError("Invalid token")


@sio.event
async def disconnect(sid):
    pass
