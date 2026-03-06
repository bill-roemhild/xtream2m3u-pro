#!/usr/bin/env sh
set -eu

TLS_CERT_FILE="${SSL_CERT_FILE:-/data/tls/tls.crt}"
TLS_KEY_FILE="${SSL_KEY_FILE:-/data/tls/tls.key}"
TLS_CERT_DIR="$(dirname "$TLS_CERT_FILE")"
TLS_SUBJECT="${SSL_CERT_SUBJECT:-/CN=xtream2m3u.local}"
PORT="${PORT:-5000}"

mkdir -p "$TLS_CERT_DIR"

if [ ! -s "$TLS_CERT_FILE" ] || [ ! -s "$TLS_KEY_FILE" ]; then
  echo "Generating self-signed TLS certificate at $TLS_CERT_FILE"
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$TLS_KEY_FILE" \
    -out "$TLS_CERT_FILE" \
    -days 3650 \
    -subj "$TLS_SUBJECT"
fi

chmod 600 "$TLS_KEY_FILE"
chmod 644 "$TLS_CERT_FILE"

exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --certfile "$TLS_CERT_FILE" \
  --keyfile "$TLS_KEY_FILE" \
  --timeout 600 \
  --workers 3 \
  --keep-alive 10 \
  run:app
