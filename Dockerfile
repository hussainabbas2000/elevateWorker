# Use official Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for subprocess tools like 'cartesia')
RUN apt-get update && \
    apt-get install -y curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files first to leverage caching
COPY pyproject.toml poetry.lock ./

# Install Python dependencies without installing the package itself
RUN poetry install --no-root --no-interaction

# Copy all code
COPY . .

# Set environment variables for production (optional, can also set on Render/Railway dashboard)
# ENV SUPABASE_URL=...
# ENV SUPABASE_ANON_KEY=...

# Start your worker
CMD ["poetry", "run", "python", "worker.py"]
