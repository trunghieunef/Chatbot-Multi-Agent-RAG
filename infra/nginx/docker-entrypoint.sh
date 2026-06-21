#!/bin/sh
# =============================================================================
# nginx entrypoint — substitutes ${DOMAIN} env var into nginx.conf
# =============================================================================
# The nginx.conf contains ${DOMAIN} placeholders that get replaced at
# container startup via envsubst, so the same image works for any domain.
# =============================================================================

set -e

# Default domain if not set (won't work for SSL, but allows container to start)
: "${DOMAIN:=localhost}"

echo "[nginx-entrypoint] DOMAIN=${DOMAIN}"

# Substitute ${DOMAIN} in the config and write to a temp location,
# then let nginx use that.
# We use envsubst but only replace ${DOMAIN} to avoid breaking nginx's own
# variables like $host, $remote_addr, etc.
envsubst '${DOMAIN}' < /etc/nginx/nginx.conf > /tmp/nginx.conf

echo "[nginx-entrypoint] Starting nginx..."
exec nginx -c /tmp/nginx.conf -g "daemon off;"
