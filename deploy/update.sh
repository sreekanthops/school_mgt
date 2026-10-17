#!/usr/bin/env bash
# deploy/update.sh — pull latest code and restart on a running server.
# Run as root (or sudo) whenever you push new commits.

set -euo pipefail
APP_DIR="/opt/school"
SYSTEM_USER="school"

echo "=== Pull latest code ==="
cd "$APP_DIR"
git pull

echo "=== Install any new Python dependencies ==="
cd "$APP_DIR/backend"
.venv/bin/pip install -r requirements.txt

echo "=== Rebuild frontend ==="
cd "$APP_DIR/frontend"
npm ci
npm run build
chown -R "$SYSTEM_USER":"$SYSTEM_USER" "$APP_DIR/frontend/dist"

echo "=== Restart API ==="
systemctl restart school-api
systemctl status school-api --no-pager

echo "=== Reload Nginx (for static asset changes) ==="
nginx -t && systemctl reload nginx

echo "=== Done. ==="
