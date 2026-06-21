#!/usr/bin/env bash
# =============================================================================
# init-letsencrypt.sh — Obtain & auto-renew SSL cert via Let's Encrypt
# =============================================================================
# Usage:
#   1. Set DOMAIN and EMAIL below (or export them)
#   2. chmod +x init-letsencrypt.sh
#   3. ./init-letsencrypt.sh
#
# This script:
#   - Starts a temporary nginx serving only HTTP (ACME challenge)
#   - Requests a certificate from Let's Encrypt
#   - Sets up auto-renewal via cron
#   - Restarts nginx with HTTPS enabled
# =============================================================================

set -euo pipefail

# =========================================================================
# CONFIG — Edit these
# =========================================================================
: "${DOMAIN:=your-domain.com}"            # Your domain, e.g. realestate.example.com
: "${EMAIL:=admin@your-domain.com}"       # Email for Let's Encrypt notifications
: "${COMPOSE_DIR:=/opt/realestate-chatbot}" # Path to docker-compose.yml

# =========================================================================
# Derived paths
# =========================================================================
CERTBOT_WWW="${COMPOSE_DIR}/infra/nginx/certbot/www"
CERTBOT_CONF="${COMPOSE_DIR}/infra/nginx/certbot/conf"
NGINX_CONF="${COMPOSE_DIR}/infra/nginx/nginx.conf"

# =========================================================================
# Pre-flight checks
# =========================================================================
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || command -v docker >/dev/null 2>&1 || { echo "ERROR: docker compose not found"; exit 1; }

if [ "$DOMAIN" = "your-domain.com" ]; then
    echo "ERROR: Please set DOMAIN (e.g., export DOMAIN=realestate.example.com)"
    exit 1
fi

echo "============================================"
echo " Let's Encrypt SSL Setup"
echo " Domain : ${DOMAIN}"
echo " Email  : ${EMAIL}"
echo "============================================"

# =========================================================================
# Step 1 — Create directories
# =========================================================================
mkdir -p "${CERTBOT_WWW}" "${CERTBOT_CONF}"

# =========================================================================
# Step 2 — Start temporary nginx for ACME challenge (HTTP only)
# =========================================================================
echo ""
echo "[1/5] Starting temporary nginx for certificate challenge..."
docker run --rm -d \
    --name certbot-nginx \
    -p 80:80 \
    -v "${CERTBOT_WWW}:/var/www/certbot:ro" \
    nginx:alpine

# =========================================================================
# Step 3 — Request certificate (dry-run first, then real)
# =========================================================================
echo ""
echo "[2/5] Dry-run certificate request..."
docker run --rm \
    -v "${CERTBOT_WWW}:/var/www/certbot" \
    -v "${CERTBOT_CONF}:/etc/letsencrypt" \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --domain "${DOMAIN}" \
    --dry-run

echo ""
echo "[3/5] Requesting real certificate..."
docker run --rm \
    -v "${CERTBOT_WWW}:/var/www/certbot" \
    -v "${CERTBOT_CONF}:/etc/letsencrypt" \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --domain "${DOMAIN}"

# =========================================================================
# Step 4 — Stop temporary nginx
# =========================================================================
echo ""
echo "[4/5] Stopping temporary nginx..."
docker stop certbot-nginx

# =========================================================================
# Step 5 — Start production nginx with HTTPS
# =========================================================================
echo ""
echo "[5/5] Starting production stack with HTTPS..."
cd "${COMPOSE_DIR}"

# Export DOMAIN so docker-compose can use it
export DOMAIN

# Copy .env if not exists and add DOMAIN
if [ -f "${COMPOSE_DIR}/.env" ]; then
    if grep -q "^DOMAIN=" "${COMPOSE_DIR}/.env" 2>/dev/null; then
        sed -i "s/^DOMAIN=.*/DOMAIN=${DOMAIN}/" "${COMPOSE_DIR}/.env"
    else
        echo "DOMAIN=${DOMAIN}" >> "${COMPOSE_DIR}/.env"
    fi
fi

# Start nginx + certbot renewal service
docker compose up -d --build nginx certbot

# Wait a moment and test
sleep 3
echo ""
echo "============================================"
echo " Testing HTTPS..."
echo "============================================"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "https://${DOMAIN}/" || echo "NOTE: If curl fails, wait a minute for DNS/cert propagation and retry"

# =========================================================================
# Step 6 — Setup auto-renew cron (on host)
# =========================================================================
echo ""
echo "============================================"
echo " Auto-renew setup"
echo "============================================"
CRON_JOB="0 3 * * * cd ${COMPOSE_DIR} && docker compose run --rm certbot renew --quiet && docker compose exec nginx nginx -s reload"
if crontab -l 2>/dev/null | grep -q "certbot renew"; then
    echo "[SKIP] Certbot cron job already exists"
else
    (crontab -l 2>/dev/null; echo "${CRON_JOB}") | crontab -
    echo "[OK] Added daily certbot renewal cron job (runs at 3 AM)"
fi

echo ""
echo "============================================"
echo " DONE! Visit: https://${DOMAIN}"
echo "============================================"
echo ""
echo " Manual renewal test:"
echo "   docker compose run --rm certbot renew --dry-run"
echo ""
echo " Force renewal:"
echo "   docker compose run --rm certbot renew --force-renewal"
echo ""
echo " Check cert expiry:"
echo "   docker compose run --rm certbot certificates"
