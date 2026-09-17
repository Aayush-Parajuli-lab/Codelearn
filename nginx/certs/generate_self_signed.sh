#!/bin/sh
# Generates a self-signed certificate for LOCAL TESTING of the TLS
# nginx config only. Browsers will show a security warning for a
# self-signed cert — that's expected and fine for local dev.
#
# For a real deployment, replace fullchain.pem/privkey.pem with a real
# certificate instead (e.g. via certbot/Let's Encrypt, or your
# hosting provider's certificate).
#
# Usage: sh nginx/certs/generate_self_signed.sh [hostname]
set -e

cd "$(dirname "$0")"
HOSTNAME="${1:-localhost}"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -days 365 \
  -subj "/CN=${HOSTNAME}" \
  -addext "subjectAltName=DNS:${HOSTNAME}"

echo ""
echo "Generated nginx/certs/fullchain.pem and nginx/certs/privkey.pem for ${HOSTNAME}."
echo "These are self-signed — browsers will warn. Fine for local testing only."
