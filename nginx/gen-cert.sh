#!/usr/bin/env bash
# Generate a self-signed TLS certificate for local / acceptance testing.
# Output: nginx/certs/cert.pem and nginx/certs/privkey.pem
#
# Usage:  bash nginx/gen-cert.sh [hostname]
#         hostname defaults to "blocklist.local"

set -euo pipefail

HOST="${1:-blocklist.local}"
CERT_DIR="$(dirname "$0")/certs"

mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days 825 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out    "$CERT_DIR/cert.pem" \
  -subj   "/CN=${HOST}/O=Blocklist Manager/C=US" \
  -addext "subjectAltName=DNS:${HOST},DNS:localhost,IP:127.0.0.1"

echo "Certificate generated:"
echo "  $CERT_DIR/cert.pem"
echo "  $CERT_DIR/privkey.pem"
echo ""
echo "Valid for 825 days.  CN=${HOST}"
