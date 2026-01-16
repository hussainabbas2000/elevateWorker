#!/bin/bash
set -e

echo "🚀 Booting worker..."

export PATH="$HOME/.cartesia/bin:$PATH"

echo "🔐 Logging into Cartesia CLI..."
cartesia auth login "$CARTESIA_API_KEY"

echo "🔍 Verifying auth..."
cartesia auth status

echo "🐍 Starting worker..."
exec python worker.py
