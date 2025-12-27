FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY stockstalk/ ./stockstalk/

# Install dependencies using UV
RUN uv pip install --system -e .

# Create directory for logs and config
RUN mkdir -p /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port for API server
EXPOSE 5000

# Default command (can be overridden)
CMD ["python", "-m", "stockstalk"]
