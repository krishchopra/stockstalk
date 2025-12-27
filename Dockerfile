# Stock Sentinel Dockerfile
# Multi-stage build for smaller final image

# Build stage
FROM python:3.12-slim as builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv pip install --no-cache .

# Production stage
FROM python:3.12-slim as production

# Create non-root user for security
RUN groupadd -r sentinel && useradd -r -g sentinel sentinel

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY --from=builder /app/src /app/src

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /app/data && chown -R sentinel:sentinel /app

# Switch to non-root user
USER sentinel

# Expose webhook port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()" || exit 1

# Default command - run the scheduler
CMD ["python", "-m", "stock_sentinel.main"]
