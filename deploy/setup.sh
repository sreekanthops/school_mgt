#!/usr/bin/env bash
# deploy/setup.sh — one-time server setup on a fresh Ubuntu 24.04 EC2 instance.
# Run as root (or with sudo) ONCE after first boot.
# Replace DOMAIN and REPO_URL before running.

set -euo pipefail

DOMAIN="school.example.com"          # ← your domain (must point to this EC2 IP)
REPO_URL="https://github.com/YOUR/REPO.git"  # ← your Git repo URL
APP_DIR="/opt/school"
SYSTEM_USER="school"

echo "=== 1. System update and dependencies ==="
apt-get update -y
apt-get upgrade -y
apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    nodejs npm \
    nginx \
    certbot python3-certbot-nginx \
    git curl ufw

echo "=== 2. Firewall (SSH + HTTP + HTTPS only) ==="
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "=== 3. Dedicated system user ==="
id -u "$SYSTEM_USER" &>/dev/null || useradd -r -s /bin/false -d "$APP_DIR" "$SYSTEM_USER"

echo "=== 4. Clone repository ==="
mkdir -p "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
chown -R "$SYSTEM_USER":"$SYSTEM_USER" "$APP_DIR"

echo "=== 5. Database directory ==="
mkdir -p "$APP_DIR/db"
chown "$SYSTEM_USER":"$SYSTEM_USER" "$APP_DIR/db"

echo "=== 6. Backend — Python virtual environment ==="
cd "$APP_DIR/backend"
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "=== 7. Backend — .env ==="
if [ ! -f "$APP_DIR/backend/.env" ]; then
    cp "$APP_DIR/backend/.env.example" "$APP_DIR/backend/.env"
    # Generate a random JWT secret automatically
    JWT_SECRET=$(.venv/bin/python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    sed -i "s|CHANGE_ME_generate_a_random_secret|$JWT_SECRET|" "$APP_DIR/backend/.env"
    echo ""
    echo ">>> .env created. Edit $APP_DIR/backend/.env and fill in:"
    echo "    - DATABASE_URL (SQLite path is already set)"
    echo "    - CORS_ORIGINS  (replace school.example.com with $DOMAIN)"
    echo "    - SMTP_USER / SMTP_PASSWORD (Gmail App Password, optional)"
    echo ""
fi
chown "$SYSTEM_USER":"$SYSTEM_USER" "$APP_DIR/backend/.env"
chmod 600 "$APP_DIR/backend/.env"

echo "=== 8. Frontend — build ==="
cd "$APP_DIR/frontend"
npm ci
npm run build
chown -R "$SYSTEM_USER":"$SYSTEM_USER" "$APP_DIR/frontend/dist"

echo "=== 9. Systemd service ==="
cp "$APP_DIR/deploy/school-api.service" /etc/systemd/system/school-api.service
systemctl daemon-reload
systemctl enable school-api
systemctl start school-api

echo "=== 10. Nginx ==="
cp "$APP_DIR/deploy/nginx-school.conf" /etc/nginx/sites-available/school
ln -sf /etc/nginx/sites-available/school /etc/nginx/sites-enabled/school
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "=== 11. TLS certificate (Let's Encrypt) ==="
echo "Run this after DNS is pointing at this server:"
echo "  sudo certbot --nginx -d $DOMAIN"
echo ""
echo "=== Setup complete ==="
echo "API health: curl http://127.0.0.1:8000/api/health"
echo "Site:       https://$DOMAIN  (after certbot)"
