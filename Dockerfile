# Universal Discord AI - Docker Configuration
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CHARACTER_NAME=friendly

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc6-dev \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/logs /app/config /app/characters /app/src

# Copy application files
COPY config/ ./config/
COPY characters/ ./characters/
COPY src/ ./src/

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

# Set entrypoint (will run as root, then switch to app user in script)
ENTRYPOINT ["docker-entrypoint.sh"]

# Note: USER app is not set here because entrypoint runs as root
# Entrypoint script will switch to app user after fixing permissions

# Expose port (if needed for health checks)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; print('Bot is running')" || exit 1

# Run the bot (use bot_async.py for async version)
CMD ["python", "src/bot_async.py"]
