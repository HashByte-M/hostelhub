<div align="center">

<img src="https://img.shields.io/badge/RGIPT-HostelHub-3B82F6?style=for-the-badge&labelColor=0d1117" alt="HostelHub"/>

# 🏛 HostelHub 

**Full-stack hostel management system for Rajiv Gandhi Institute of Petroleum Technology, Jais, Amethi.**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/Neon_PostgreSQL-asyncpg-336791?style=flat-square&logo=postgresql&logoColor=white)](https://neon.tech)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-realtime-010101?style=flat-square&logo=socket.io)](https://socket.io)
[![Razorpay](https://img.shields.io/badge/Razorpay-payments-02042B?style=flat-square&logo=razorpay)](https://razorpay.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

[Features](#-features) · [Tech Stack](#-tech-stack) · [Quick Start](#-quick-start) · [API Reference](#-api-reference) · [Roles](#-roles--permissions) · [Hostels](#-hostel-blocks)

</div>

---

## 📋 Table of Contents

- [About](#-about)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [Roles & Permissions](#-roles--permissions)
- [Hostel Blocks](#-hostel-blocks)
- [Database Schema](#-database-schema)
- [Real-time Events](#-real-time-events-socketio)
- [Contributing](#-contributing)

---

## 🏠 About

HostelHub is a comprehensive hostel management portal serving **students, hostel reps, mess & maintenance secretaries, wardens, and super-admins** across all RGIPT hostel blocks.

- **Backend** — FastAPI + asyncpg on Neon PostgreSQL, real-time push via Socket.IO
- **Frontend** — Single-file Vanilla JS with a Claymorphism design system, full dark mode, Chart.js analytics
- **Payments** — Razorpay integration for online fine settlement
- **Auth** — JWT (HS256, 24h expiry) + bcrypt + email OTP verification
- **Domain lock** — All user accounts must use an `@rgipt.ac.in` email. New accounts require admin approval before gaining access.

---

## ✨ Features

<details>
<summary><b>🔐 Auth & User Management</b></summary>

- Institutional email registration (`@rgipt.ac.in` only)
- Email OTP verification (10-minute expiry via SMTP/Gmail)
- JWT login with 24-hour token expiry
- bcrypt password hashing
- Role-based access control across 7 roles
- Admin approval queue for new accounts
- Super-admin can approve, reject, reassign roles, and delete users

</details>

<details>
<summary><b>📢 Announcements & Notice Board</b></summary>

- Block-targeted notices with categories and custom tags
- Wardens and head wardens can broadcast to all blocks simultaneously
- Hostel reps post notices within their own block
- File attachments supported on notice posts (stored as JSONB)

</details>

<details>
<summary><b>🍱 Meal Menu Management</b></summary>

- Day-by-day, meal-by-meal menu (Breakfast / Lunch / Snacks / Dinner)
- Mess Secretary can update items per slot
- Students view the live weekly menu from their dashboard
- Upsert-safe — editing replaces the existing slot seamlessly

</details>

<details>
<summary><b>🔧 Maintenance Complaints</b></summary>

- Students file categorised complaints with room/area location
- Maintenance secretary assigns, updates status, and tracks resolution
- Status flow: `Open → In Progress → Resolved`
- Live push updates via Socket.IO on every status change

</details>

<details>
<summary><b>⭐ Feedback System</b></summary>

- Students submit star-rated feedback across hostel areas
- Admins view aggregated ratings per area
- Timestamped; anonymous-friendly (user ID stored but not exposed publicly)

</details>

<details>
<summary><b>💸 Fines & Online Payments</b></summary>

- Wardens issue typed fines with due dates in INR
- Students pay online via **Razorpay** (HMAC-verified)
- Cash payment can be recorded manually by admins
- Admins can waive fines with a reason
- Full audit trail: `issued_by`, `payment_method`, `payment_reference`

</details>

<details>
<summary><b>🚶 Visitor Log</b></summary>

- Hostel reps and wardens log visitor entry with relation, contact, and purpose
- Exit timestamp recorded separately
- Full searchable history per hostel block

</details>

<details>
<summary><b>🛏 Room Allocations</b></summary>

- Wardens assign students to rooms and bed numbers with validity dates
- Automatic upsert — reallocating a student updates the existing record
- Deallocate (DELETE) support
- Real-time `room_updated` Socket.IO event on every change

</details>

<details>
<summary><b>✈️ Leave Requests</b></summary>

- Students submit leave with type, dates, reason, and parent contact
- Wardens approve or reject with optional notes
- Live `new_leave_request` and `leave_updated` Socket.IO events
- Students track status in real time from the portal

</details>

<details>
<summary><b>📦 Seized Item Log</b></summary>

- Wardens log seized items with room, student, quantity, and description
- Mark items as `returned` or `disposed`
- Management dashboard shows aggregate stats

</details>

---

## 🛠 Tech Stack

### Backend

| Package | Purpose |
|---|---|
| `FastAPI` | ASGI web framework, async throughout |
| `asyncpg` | High-performance async PostgreSQL driver with connection pool |
| `python-socketio` | Socket.IO server in ASGI mode for real-time push |
| `python-jose` + `bcrypt` | JWT signing (HS256) and password hashing |
| `aiosmtplib` | Async SMTP for OTP email delivery |
| `razorpay` | Payment order creation & HMAC verification |
| `pydantic[email]` | Request/response validation and serialisation |
| `python-dotenv` | `.env` loading |

### Frontend

| Tool | Purpose |
|---|---|
| Tailwind CSS (CDN) | Utility-first styling |
| Chart.js 3.7 (CDN) | Analytics dashboard charts |
| Montserrat / Poppins / JetBrains Mono | Google Fonts |
| Vanilla JS | Zero build step — single HTML file |

### Infrastructure

| Service | Purpose |
|---|---|
| [Neon](https://neon.tech) | Serverless PostgreSQL (auto-scales to zero) |
| Razorpay | INR payment gateway |
| Any SMTP provider | OTP email delivery (Gmail works out of the box) |

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/hostelhub.git
cd hostelhub
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate.bat       # Windows
```

### 3. Install dependencies

```bash
pip install fastapi uvicorn asyncpg "python-socketio[asyncio_client]" \
            "python-jose[cryptography]" bcrypt "pydantic[email]" \
            python-dotenv aiosmtplib razorpay
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values (see section below)
```

### 5. Start the server

```bash
uvicorn hostelhub:socket_app --host 0.0.0.0 --port 8000 --reload
```

> Tables are created automatically on first startup via `_init_db()` — no migration tool needed.

| URL | Description |
|---|---|
| `http://localhost:8000` | API base |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc |

### 6. Open the frontend

Update the `API_BASE` constant at the top of `index.html` to point to your server, then open it in any browser or serve it statically:

```bash
python -m http.server 3000
# → open http://localhost:3000
```

---

## 🔧 Environment Variables

Create a `.env` file in the project root:

```env
# ── Required ──────────────────────────────────────────
DATABASE_URL=postgresql://user:pass@host/dbname
SECRET_KEY=a-long-random-string-at-least-32-characters

# ── Email / OTP ────────────────────────────────────────
SMTP_EMAIL=your-gmail@gmail.com
SMTP_PASSWORD=your-16-char-app-password   # Gmail App Password, NOT login password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# ── Razorpay (optional — disable to skip online payments) ──
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_secret
```

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Neon (or any) PostgreSQL connection string |
| `SECRET_KEY` | ✅ | JWT signing secret — change before production! |
| `SMTP_EMAIL` | ⚠️ Optional | Sender address for OTP emails |
| `SMTP_PASSWORD` | ⚠️ Optional | Gmail App Password (requires 2FA enabled) |
| `RAZORPAY_KEY_ID` | ⚠️ Optional | Razorpay key for online fine payments |
| `RAZORPAY_KEY_SECRET` | ⚠️ Optional | Razorpay secret for HMAC verification |

> **Gmail tip:** Enable 2-Factor Authentication → Google Account → Security → App Passwords → generate a 16-character password and use that as `SMTP_PASSWORD`.

---

## 📖 API Reference

All endpoints require `Authorization: Bearer <token>` unless marked **public**.

<details>
<summary><b>🔑 Authentication</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Create new account (`@rgipt.ac.in` email only) |
| `POST` | `/auth/login` | Public | Returns `{ access_token, token_type, user }` |
| `POST` | `/auth/request-otp` | Public | Send OTP to email (valid 10 min) |
| `POST` | `/auth/verify-otp` | Public | Verify OTP and return token |
| `GET` | `/auth/me` | 🔒 Bearer | Current user profile |
| `PATCH` | `/auth/me` | 🔒 Bearer | Update own profile |
| `POST` | `/auth/change-password` | 🔒 Bearer | Change password |

</details>

<details>
<summary><b>📢 Announcements & Notices</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/announcements` | 🔒 Bearer | List announcements (filter: `?hostel=b_block`) |
| `POST` | `/announcements` | 🔒 Admin | Post announcement |
| `DELETE` | `/announcements/{id}` | 🔒 Admin | Delete announcement |
| `GET` | `/notices` | 🔒 Bearer | List notice posts |
| `POST` | `/notices` | 🔒 Admin | Create notice post with attachments |
| `DELETE` | `/notices/{id}` | 🔒 Admin | Delete notice post |

</details>

<details>
<summary><b>🍱 Meal Menu</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/menu` | 🔒 Bearer | Get full weekly menu |
| `PUT` | `/menu` | 🔒 mess_secretary+ | Upsert a meal slot (`day` + `meal` + `items[]`) |

</details>

<details>
<summary><b>🔧 Complaints</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/complaints` | 🔒 Bearer | List complaints (role-filtered) |
| `POST` | `/complaints` | 🔒 Bearer | Submit complaint |
| `PATCH` | `/complaints/{id}` | 🔒 maint_secretary+ | Update status / assignee |

</details>

<details>
<summary><b>💸 Fines & Payments</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/fines` | 🔒 Bearer | List fines (own / all for admins) |
| `POST` | `/fines` | 🔒 warden+ | Issue a fine |
| `POST` | `/fines/{id}/pay` | 🔒 Bearer | Create Razorpay order → `{ order_id, key_id, amount }` |
| `POST` | `/fines/{id}/verify` | 🔒 Bearer | Verify HMAC & mark paid |
| `PATCH` | `/fines/{id}/cash` | 🔒 warden+ | Record cash payment |
| `PATCH` | `/fines/{id}/waive` | 🔒 warden+ | Waive fine with reason |

</details>

<details>
<summary><b>✈️ Leave Requests</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/leave` | 🔒 Bearer | List own leave requests |
| `POST` | `/leave` | 🔒 Bearer | Submit leave request |
| `PATCH` | `/leave/{id}` | 🔒 warden+ | Approve / reject with notes |

</details>

<details>
<summary><b>🚶 Visitor Log</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/visitors` | 🔒 hostel_rep+ | List visitors (filter: `?hostel=`) |
| `POST` | `/visitors` | 🔒 hostel_rep+ | Log visitor entry |
| `PATCH` | `/visitors/{id}/exit` | 🔒 hostel_rep+ | Record exit time |

</details>

<details>
<summary><b>🛏 Room Allocations</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/rooms` | 🔒 warden+ | List allocations (filter: `?hostel=`) |
| `POST` | `/rooms` | 🔒 warden+ | Allocate / update room (upserts) |
| `DELETE` | `/rooms/{id}` | 🔒 warden+ | Remove allocation |

</details>

<details>
<summary><b>📦 Seized Items</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/items` | 🔒 warden+ | List seized items |
| `POST` | `/items` | 🔒 warden+ | Log seized item |
| `PATCH` | `/items/{id}` | 🔒 warden+ | Update status (`returned` / `disposed`) |

</details>

<details>
<summary><b>👥 Admin / User Management</b></summary>

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/admin/users/pending` | 🔒 super_admin | List pending approvals |
| `POST` | `/admin/users/{id}/approve` | 🔒 super_admin | Approve account |
| `DELETE` | `/admin/users/{id}/reject` | 🔒 super_admin | Reject & delete account |
| `GET` | `/admin/users` | 🔒 super_admin | List all users |
| `PATCH` | `/admin/users/{id}` | 🔒 super_admin | Update role / hostel |
| `DELETE` | `/admin/users/{id}` | 🔒 super_admin | Permanently delete user |
| `GET` | `/users/search` | 🔒 warden+ | Search students by name/email |
| `GET` | `/hostels` | 🔒 Bearer | List all hostel block IDs and names |

</details>

---

## 👤 Roles & Permissions

Roles are strictly hierarchical. Higher roles inherit all permissions below them.

```
super_admin        ← Full access, all hostels, cross-block
    │
head_warden        ← Cross-block authority, all warden powers
    │
warden             ← Fines, items, rooms, visitors, leave approvals
    │
mess_secretary     ← Meal menus, feedback view
maint_secretary    ← Complaint management & assignment
    │
hostel_rep         ← Block notices, visitor logging
    │
student            ← Read own data, submit complaints / leave / feedback
```

| Role | Cross-Block | Fines | Rooms | Complaints | Menu | Visitors |
|---|---|---|---|---|---|---|
| `super_admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `head_warden` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `warden` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `mess_secretary` | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `maint_secretary` | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `hostel_rep` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `student` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 🏠 Hostel Blocks

Use these exact IDs in all API requests (`hostel` fields, query params, etc.).

| Block ID | Display Name | Gender |
|---|---|---|
| `asima_chatterjee` | Asima Chatterjee Hostel | 🟣 Girls |
| `a_block` | A Block | 🟣 Girls |
| `b_block` | B Block | 🔵 Boys |
| `c_block` | C Block | 🔵 Boys |
| `d_block` | D Block | 🔵 Boys |
| `e_block` | E Block | 🔵 Boys |
| `f_block` | F Block | 🔵 Boys |
| `g_block` | G Block | 🔵 Boys |
| `h_block` | H Block | 🔵 Boys |
| `all` | All Hostels | — |

---

## 🗄 Database Schema

All tables are created automatically by `_init_db()` on server startup — no migration tool required.

| Table | Description |
|---|---|
| `users` | Accounts with role, hostel, approval status |
| `announcements` | Admin-posted announcements with category/tag |
| `notice_posts` | Block-targeted notices with JSONB attachments |
| `meal_menu` | Weekly meal slots (unique on `day + meal`) |
| `complaints` | Student complaints with status and assignee |
| `feedback` | Star-rated feedback by area |
| `fines` | Fines with Razorpay order tracking |
| `seized_items` | Items logged by wardens with status |
| `leave_requests` | Student leave with approval tracking |
| `visitor_log` | Visitor entry/exit log per block |
| `room_allocations` | Student ↔ room/bed mapping with validity |

---

## ⚡ Real-time Events (Socket.IO)

Connect with a valid JWT token:

```javascript
const socket = io("http://localhost:8000", {
  auth: { token: "your-jwt-token" }
});
```

| Event | Fired when |
|---|---|
| `new_announcement` | An announcement is posted |
| `complaint_updated` | Complaint status or assignee changes |
| `new_leave_request` | A student submits a leave request |
| `leave_updated` | Warden approves or rejects a leave |
| `room_updated` | A room allocation is created or changed |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch — `git checkout -b feat/your-feature`
3. Commit your changes — `git commit -m "feat: add your feature"`
4. Push to the branch — `git push origin feat/your-feature`
5. Open a Pull Request

Please follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

---

<div align="center">

Built with ❤️ for RGIPT · Jais, Amethi

</div>
