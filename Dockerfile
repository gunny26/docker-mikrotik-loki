# Multi-stage build for smaller final image
FROM alpine:3.20 AS builder

# Install build dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-virtualenv \
    gcc \
    musl-dev \
    python3-dev

# Create virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies
RUN pip install --no-cache-dir --disable-pip-version-check requests routeros_api 




# Final stage
FROM alpine:3.20

# Set timezone
ENV TZ=Europe/Vienna

# Install only runtime dependencies (without Python packages - they're in venv)
RUN apk add --no-cache \
    python3 \
    tzdata \
    curl \
    ca-certificates \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user (Alpine doesn't have ubuntu user)
RUN addgroup -g 1000 appuser && \
    adduser -u 1000 -G appuser -D -h /app appuser

# Set working directory
WORKDIR /app

# Copy application files with correct ownership
COPY --chown=appuser:appuser build/main.py ./main.py

# Switch to non-root user
USER appuser

# Use exec form and proper signal handling
CMD ["python3", "-u", "main.py"]
