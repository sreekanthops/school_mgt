# EC2 Deployment Guide — School Management Suite

End-to-end steps to launch the app on an AWS EC2 instance with Nginx, TLS (Let's Encrypt), and systemd.

---

## Architecture overview

```
Browser (HTTPS :443)
       │
       ▼
   [ Nginx ]
   ├── /         → serves React SPA from /opt/school/frontend/dist (static files)
   └── /api/*    → reverse-proxies to Uvicorn at 127.0.0.1:8000 (FastAPI)

   [ Uvicorn ]   → bound to 127.0.0.1:8000, managed by systemd, runs as non-root user
   [ SQLite DB ] → /opt/school/db/school.db  (or PostgreSQL — see .env.example)
```

Everything runs on a single EC2 instance.
Nginx terminates TLS and serves the static frontend with long-lived cache headers.
The API is never exposed directly to the internet (bound to 127.0.0.1 only).

---

## 1. Prerequisites

| What | Minimum |
|---|---|
| EC2 instance | t3.small (2 vCPU, 2 GB RAM) or larger |
| OS | Ubuntu 24.04 LTS (recommended) |
| Storage | 20 GB gp3 root volume |
| Security Group inbound | SSH (22), HTTP (80), HTTPS (443) |
| Domain name | An A record pointing to the EC2 Elastic IP |

> **Elastic IP:** assign one to your instance so the IP does not change on restart.
> (EC2 → Elastic IPs → Allocate → Associate)

---

## 2. Launch and connect to EC2

### 2a. Launch the instance (AWS Console)

1. **EC2 → Launch Instance**
2. AMI: **Ubuntu Server 24.04 LTS (HVM)**, 64-bit (x86)
3. Instance type: **t3.small** (or t3.medium for heavier use)
4. Key pair: create or select an existing `.pem` key
5. Network settings:
   - Allow SSH from your IP only
   - Allow HTTP (80) from anywhere
   - Allow HTTPS (443) from anywhere
6. Storage: **20 GiB gp3**
7. Launch

### 2b. Assign an Elastic IP

```
EC2 → Elastic IPs → Allocate Elastic IP address → Allocate
Select the new IP → Actions → Associate Elastic IP → choose your instance → Associate
```

### 2c. Point your domain to the Elastic IP

Create an **A record** in your DNS provider:

```
Type  Name                   Value
A     school.example.com     <your Elastic IP>
```

DNS propagation takes a few minutes to an hour.

### 2d. SSH into the instance

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<your-elastic-ip>
```

---

## 3. One-time server setup

### 3a. Edit the setup script

On your local machine, open `deploy/setup.sh` and set the two variables at the top:

```bash
DOMAIN="school.example.com"          # your real domain
REPO_URL="https://github.com/YOUR/REPO.git"  # your Git repo URL
```

Commit and push that change, then on the EC2 instance:

```bash
# Install git first, clone the repo, then run the setup script
sudo apt-get update -y && sudo apt-get install -y git
sudo git clone https://github.com/YOUR/REPO.git /opt/school
sudo bash /opt/school/deploy/setup.sh
```

The script will:
- Install Python 3.12, Node 20, Nginx, Certbot
- Configure UFW firewall (SSH + Nginx Full only)
- Create a `school` system user (non-root, no shell)
- Set up the Python virtual environment and install dependencies
- Copy `.env.example` → `.env` with an auto-generated `JWT_SECRET`
- Build the React frontend
- Install and start the `school-api` systemd service
- Configure Nginx

### 3b. Edit the `.env` file

```bash
sudo nano /opt/school/backend/.env
```

Required changes:

```bash
# Set your actual domain for CORS
CORS_ORIGINS=https://school.example.com

# JWT_SECRET is already auto-generated — do not change it unless you want to
# invalidate all existing sessions

# Optional: Gmail App Password for owner email recovery
SMTP_USER=your-gmail@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail App Password (not your real password)
SMTP_FROM=your-gmail@gmail.com
```

> **Gmail App Password:** go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create an app password for "Mail". Use that 16-character password, not your Gmail login password.

After editing:

```bash
sudo systemctl restart school-api
```

### 3c. Obtain a TLS certificate (Let's Encrypt)

> DNS must be pointing at your server before this step.

```bash
sudo certbot --nginx -d school.example.com
```

Certbot will:
- Verify domain ownership (HTTP-01 challenge)
- Obtain a certificate from Let's Encrypt
- Automatically edit the Nginx config to add the certificate paths and the HTTP→HTTPS redirect

Accept the prompts. When asked about redirecting HTTP → HTTPS choose **Redirect** (option 2).

Auto-renewal is set up by certbot automatically. Verify it:

```bash
sudo certbot renew --dry-run
```

---

## 4. Verify the deployment

```bash
# API health check (from the server)
curl http://127.0.0.1:8000/api/health
# Expected: {"status":"ok"}

# From your browser
https://school.example.com          # should load the React app
https://school.example.com/docs     # FastAPI interactive docs (disable in prod if desired)

# Systemd service status
sudo systemctl status school-api

# Nginx status
sudo systemctl status nginx

# Application logs
sudo journalctl -u school-api -f
```

---

## 5. First-time application setup

```bash
# SSH into the server
sudo -u school bash
cd /opt/school/backend

# Option A: fresh database with demo data (generates logins + passwords into .env)
.venv/bin/python -m app.seed --reset
grep PASSWORD /opt/school/backend/.env    # shows generated demo passwords

# Option B: fresh empty database (no demo data)
# The database is created automatically on first API start — no command needed.
# Visit the app, create the superadmin, then add schools.
```

---

## 6. Deploying updates

Whenever you push new commits to the repo:

```bash
sudo bash /opt/school/deploy/update.sh
```

This script:
1. `git pull` — fetches latest code
2. Installs any new Python packages
3. Rebuilds the React frontend
4. Restarts the API service
5. Reloads Nginx

---

## 7. File and directory layout on the server

```
/opt/school/
├── backend/
│   ├── .env                  ← secrets (chmod 600, owned by school user)
│   ├── .env.example          ← template (committed to git)
│   ├── .venv/                ← Python virtual environment
│   ├── app/                  ← FastAPI application
│   └── uploads/              ← user-uploaded photos (git-ignored)
├── frontend/
│   ├── dist/                 ← built React SPA (served by Nginx)
│   └── src/                  ← source (not served)
├── db/
│   └── school.db             ← SQLite database (git-ignored)
└── deploy/
    ├── nginx-school.conf     ← Nginx site config (symlinked into sites-enabled)
    ├── school-api.service    ← systemd unit file
    ├── setup.sh              ← one-time setup
    └── update.sh             ← rolling update
```

---

## 8. Nginx config explained

File: [`deploy/nginx-school.conf`](deploy/nginx-school.conf)

| Block | What it does |
|---|---|
| `server { listen 80 }` | Redirects all HTTP to HTTPS |
| `ssl_protocols TLSv1.2 TLSv1.3` | Disables TLS 1.0 and 1.1 |
| `ssl_ciphers ...` | Strong cipher suite (IBM security policy compliant) |
| `Strict-Transport-Security` | HSTS — forces HTTPS for 2 years |
| `location /` | Serves React SPA; `try_files` falls back to `index.html` for client-side routing |
| `location ~* \.js$` etc. | 1-year browser cache for Vite fingerprinted assets |
| `location /api/` | Reverse proxy to Uvicorn at 127.0.0.1:8000 |
| `client_max_body_size 6m` | Allows photo uploads (3 MB) and Smart Import files (5 MB) |

---

## 9. Systemd service explained

File: [`deploy/school-api.service`](deploy/school-api.service)

| Setting | Why |
|---|---|
| `User=school` | Never runs as root |
| `--host 127.0.0.1` | API is only reachable via Nginx, never directly from the internet |
| `--workers 2` | Two Uvicorn worker processes (adjust for instance size) |
| `EnvironmentFile=…/.env` | Secrets from `.env` file, not baked into the unit |
| `NoNewPrivileges=yes` | Systemd hardening — service cannot escalate privileges |
| `PrivateTmp=yes` | Isolated /tmp |
| `ReadWritePaths=…` | Only the DB directory and uploads are writable |
| `Restart=always` | Auto-restarts on crash |

---

## 10. Database

### SQLite (default)
Fine for single-server deployments with up to a few thousand active users.
The database file is at `/opt/school/db/school.db`.

**Backup:**
```bash
# Simple copy (safe because SQLite WAL mode handles concurrent reads)
sudo -u school cp /opt/school/db/school.db /opt/school/db/school.db.bak

# Or use SQLite's online backup (fully safe under load)
sudo -u school /opt/school/backend/.venv/bin/python3 \
    -c "import sqlite3; s=sqlite3.connect('/opt/school/db/school.db'); \
        d=sqlite3.connect('/opt/school/db/backup.db'); s.backup(d)"
```

**Automated nightly backup to S3:**
```bash
# Add to root crontab (crontab -e)
0 2 * * * aws s3 cp /opt/school/db/school.db s3://your-bucket/school-$(date +\%Y\%m\%d).db
```

### PostgreSQL (optional, for higher load)
1. Install: `sudo apt-get install -y postgresql`
2. Create DB and user:
   ```sql
   CREATE USER school_user WITH PASSWORD 'CHANGE_ME';
   CREATE DATABASE school_db OWNER school_user;
   ```
3. In `/opt/school/backend/.env`:
   ```
   DATABASE_URL=postgresql://school_user:CHANGE_ME@localhost:5432/school_db
   ```
4. Install the driver: `.venv/bin/pip install psycopg2-binary`
5. Restart: `sudo systemctl restart school-api`

---

## 11. Useful commands

```bash
# View live API logs
sudo journalctl -u school-api -f

# Restart the API
sudo systemctl restart school-api

# Check Nginx config syntax
sudo nginx -t

# Reload Nginx (pick up static file changes without downtime)
sudo systemctl reload nginx

# Check certificate expiry
sudo certbot certificates

# Force certificate renewal
sudo certbot renew

# Open a Python shell with the app loaded (for debugging)
cd /opt/school/backend
sudo -u school .venv/bin/python3 -c "from app.db import engine; print(engine)"
```

---

## 12. Security checklist

- [x] API binds to 127.0.0.1 only (never 0.0.0.0)
- [x] TLS 1.2 / 1.3 only (TLS 1.0 and 1.1 disabled)
- [x] Strong cipher suite
- [x] HSTS header
- [x] Service runs as non-root `school` user
- [x] Secrets in `.env` (chmod 600, git-ignored)
- [x] Firewall: only ports 22, 80, 443 open
- [x] `NoNewPrivileges` and `PrivateTmp` in systemd unit
- [ ] Disable `/docs` endpoint in production (optional):
      In `backend/app/main.py` change `docs_url="/docs"` to `docs_url=None`
- [ ] Set up automated DB backups (see §10)
- [ ] Enable EC2 CloudWatch monitoring or an uptime check

---

## 13. Troubleshooting

| Symptom | Check |
|---|---|
| `502 Bad Gateway` | `sudo systemctl status school-api` — the API is down; check `journalctl -u school-api` |
| API starts then crashes | `journalctl -u school-api -n 50` — likely a bad `.env` value |
| CORS error in browser | Check `CORS_ORIGINS` in `.env` matches your exact domain (include `https://`) |
| Certificate error | Run `sudo certbot renew`; check DNS A record points to EC2 IP |
| `413 Request Entity Too Large` | Nginx `client_max_body_size` — already set to 6m in the config |
| Login sessions lost after restart | `JWT_SECRET` is not set in `.env` (ephemeral secret is regenerated on each restart) |
| Emails not sending | Check `SMTP_USER`/`SMTP_PASSWORD` in `.env`; use a Gmail App Password, not your Gmail login |
| Static files return 404 | Run `npm run build` inside `frontend/`, then `sudo systemctl reload nginx` |
