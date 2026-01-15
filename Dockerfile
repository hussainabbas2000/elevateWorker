FROM python:3.11-slim

# Install all dependencies in one step
RUN apt-get update && \
    apt-get install -y curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://cartesia.sh | sh && \
    pip install cartesia supabase

# Rest of the Dockerfile remains the same
ENV PATH="/root/.cartesia/bin:${PATH}"
WORKDIR /elevateWorker
COPY . .
ENV CARTESIA_HOME=/app/.cartesia
ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]