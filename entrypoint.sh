#!/bin/bash
set -e

echo "🔐 Writing Cartesia credentials (XDG config)..."

CONFIG_DIR="/root/.config/cartesia"
CONFIG_FILE="$CONFIG_DIR/config.json"

mkdir -p "$CONFIG_DIR"

cat <<EOF > "$CONFIG_FILE"
{
  "api_key": "${CARTESIA_API_KEY}"
}
EOF

chmod 600 "$CONFIG_FILE"

echo "✅ Cartesia credentials written to $CONFIG_FILE"

echo "🔍 Verifying auth..."
/root/.cartesia/bin/cartesia auth status || true

echo "🚀 Starting worker..."
exec python worker.py
