#!/bin/bash
set -e

echo "🔐 Writing Cartesia credentials..."

mkdir -p /root/.cartesia

cat <<EOF > /root/.cartesia/credentials.json
{
  "api_key": "${CARTESIA_API_KEY}"
}
EOF

chmod 600 /root/.cartesia/credentials.json

echo "✅ Cartesia credentials written"

exec python worker.py
