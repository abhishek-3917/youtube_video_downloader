# Stage 1: Grab official Deno binary for YouTube EJS challenge solver
FROM denoland/deno:bin AS deno-bin

# Stage 2: Application container
FROM python:3.11-slim

# Copy Deno into PATH (enabled by default by yt-dlp to solve YouTube JS challenges)
COPY --from=deno-bin /deno /usr/local/bin/deno

# Install system dependencies: ffmpeg, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements (including yt-dlp[default] which includes yt-dlp-ejs)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure downloads directory exists
RUN mkdir -p downloads

# Port and server startup
ENV PORT=8000
ENV HOST=0.0.0.0
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
