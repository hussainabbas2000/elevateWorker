FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cartesia supabase

WORKDIR /elrevateWorker
COPY . .

# 🔥 CRITICAL
ENV CARTESIA_HOME=/app/.cartesia
ENV PYTHONUNBUFFERED=1

CMD ["python", "worker.py"]