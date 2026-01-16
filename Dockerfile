FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl ca-certificates bash wget && \
    rm -rf /var/lib/apt/lists/*

# Debug: Check curl works
RUN curl --version

# Download and inspect the installation script
RUN curl -fsSL https://cartesia.sh -o /tmp/install.sh && \
    cat /tmp/install.sh && \
    bash /tmp/install.sh

# Add Cartesia CLI to PATH
ENV PATH="/root/.cartesia/bin:${PATH}"

# Install Python dependencies
RUN pip install cartesia supabase

# Debug: Check what was installed
RUN ls -la /root/.cartesia/ || echo "No .cartesia directory" && \
    ls -la /root/.cartesia/bin/ || echo "No bin directory" && \
    which cartesia || echo "cartesia not in PATH"

# Set working directory
WORKDIR /elevateWorker
COPY . .

# Environment variables
ENV CARTESIA_HOME=/app/.cartesia
ENV PYTHONUNBUFFERED=1

CMD ["python", "worker.py"]