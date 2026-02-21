#!/bin/bash
# Generate self-signed TLS certificates for local development.
# For production, use Let's Encrypt or another public CA.
#
# Usage: ./ssl/generate-dev-certs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout "$SCRIPT_DIR/privkey.pem" \
  -out "$SCRIPT_DIR/fullchain.pem" \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:webapp.local,DNS:camoufox.local,DNS:webcrawler.local"

echo "Dev certificates generated in $SCRIPT_DIR/"
echo "  fullchain.pem  (certificate)"
echo "  privkey.pem    (private key)"
