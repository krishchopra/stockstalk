# StockStalk Dockerfile
# Multi-stage build for smaller final image

# Build stage
FROM python:3.11-slim AS builder

# Install UV package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY stockstalk/ ./stockstalk/

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv pip install --no-cache .

# Production stage
FROM python:3.11-slim AS production

# Create non-root user for security
RUN groupadd -r stockstalk && useradd -r -g stockstalk stockstalk

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY --from=builder /app/stockstalk /app/stockstalk

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs && chown -R stockstalk:stockstalk /app

# Switch to non-root user
USER stockstalk

# Expose port for FastAPI server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

# Default command - run the scheduler
CMD ["python", "-m", "stockstalk"]
