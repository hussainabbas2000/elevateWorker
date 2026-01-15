FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Cartesia CLI
RUN curl -fsSL https://cartesia.sh | sh

# Add Cartesia CLI to PATH
ENV PATH="/root/.cartesia/bin:${PATH}"

# Install Python dependencies
RUN pip install cartesia supabase

# Verify Cartesia CLI is installed
RUN which cartesia && cartesia --help || echo "Warning: cartesia CLI not found"

# Set working directory
WORKDIR /elevateWorker
COPY . .

# Environment variables
ENV CARTESIA_HOME=/app/.cartesia
ENV PYTHONUNBUFFERED=1

CMD ["python", "worker.py"]