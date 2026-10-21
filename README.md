# NU10 Interview Scheduler

A starter full-stack application: FastAPI backend, responsive frontend, database persistence, Resend email delivery, single-use booking behavior, admin dashboard, and scheduled reminder worker.

## 1. Install Python
Install Python 3.11 or 3.12 from https://www.python.org/downloads/ . On Windows, tick **Add Python to PATH** during setup.

## 2. Open the project in VS Code
Extract the ZIP. In VS Code choose **File → Open Folder** and select `nu10-interview-scheduler`.

## 3. Create environment file
Copy `.env.example`, name the copy `.env`, then edit `.env`:
- Set a long unique `ADMIN_PASSWORD`.
- Add your `RESEND_API_KEY`.
- Set `EMAIL_FROM` to a sender address that Resend permits.
- Set `PUBLIC_BASE_URL` to your public deployed URL when deployed. Locally, leave the default.

Do not upload `.env` to GitHub. The included `.gitignore` helps prevent that.

## 4. Install and run (Windows)
Open **Terminal → New Terminal** in VS Code and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

If PowerShell blocks activation, run this instead in Command Prompt terminal:
```bat
.venv\Scripts\activate.bat
```

Open http://127.0.0.1:8000

## 5. Configure Resend
Create an account at https://resend.com/ and create an API key. Resend may restrict sending to your own verified address until you verify a domain. For production, add the DNS records Resend supplies at the provider that manages your domain. `EMAIL_FROM` must use an authorized sender. Never put the API key in frontend JavaScript.

The NU10 logo is shown in email using a public image URL. Once deployed, `PUBLIC_BASE_URL` must point to the live HTTPS website so recipients can load the logo and booking links.

## 6. Admin login
Click **Admin login** in the top-right corner. Use `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env`. Admin APIs use HTTP Basic authentication over HTTPS. Do not expose the site publicly until HTTPS and a strong password are configured. For a multi-user business deployment, replace the shared admin login with individual accounts, roles, and audit logging.

## 7. How to test
1. Open the site and log in as admin.
2. Enter candidate and interviewer details using email addresses that you are allowed to send to.
3. Add one or more future slots.
4. Click **Save & send invitation**.
5. Open the candidate's email and click one slot.
6. Check the confirmation emails and meeting link.
7. Return to the admin page; it refreshes every 10 seconds. Click **View** for details.

## 8. Public deployment (overview)
Use a host that supports a long-running Python web service and persistent PostgreSQL. Set the start command to:
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```
Set these environment variables in the host dashboard:
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `RESEND_API_KEY`
- `EMAIL_FROM`
- `PUBLIC_BASE_URL=https://YOUR-PUBLIC-DOMAIN`
- `DATABASE_URL=postgresql+psycopg://...` (use the host's PostgreSQL URL and adapt scheme if necessary)
- optional `TA_NOTIFICATION_EMAIL`

Upload the `static/nu10logo.jpg` file as part of the project. Use HTTPS. Keep the service and reminder worker running. This starter runs the reminder scan inside the web process, so run exactly one app instance or move reminders into a dedicated worker before scaling to multiple instances.

## Important production hardening
This is a functional starter, not a security/compliance certification. Before handling real candidate data at scale, add individual user accounts/roles, CSRF/rate limits, audit logs, retention/deletion policy, backup/restore tests, monitoring, email bounce/webhook processing, and a dedicated persistent reminder worker. A Jitsi URL is generated automatically but is not a private meeting room. Confirm your organization's privacy and meeting-security requirements.
