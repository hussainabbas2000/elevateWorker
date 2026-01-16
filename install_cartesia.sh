#!/usr/bin/env bash
set -e

curl -fsSL https://cartesia.sh | sh

export PATH="$HOME/.cartesia/bin:$PATH"

cartesia auth status || true
cartesia --version
