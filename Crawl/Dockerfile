# ============================================================
# batdongsancom-crawler  —  Multi-stage Docker build
# ============================================================
# Stage 1: Install Python deps + Playwright browsers
# Stage 2: Slim runtime image with only what's needed
# ============================================================

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install OS-level deps needed to install Playwright browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser + its OS dependencies
RUN playwright install --with-deps chromium


# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# Install runtime OS libraries Chromium needs
# (fonts, graphics libs, dbus, nss, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium runtime deps
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libgbm1 \
    # Fonts for rendering Vietnamese text
    fonts-noto-cjk \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy Playwright browsers from builder
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Copy application code
COPY crawl_listing_url.py .
COPY crawl_listing_details.py .
COPY merge.py .
COPY clean.py .
COPY heatmap.py .

# Data volume: mount CSVs here so they persist across container restarts
# Input:  /data/listing_url.csv
# Output: /data/listing_details.csv
VOLUME /data

# Default entrypoint — can be overridden at runtime
ENTRYPOINT ["python"]
CMD ["crawl_listing_details.py", "--input", "/data/listing_url.csv", "--output", "/data/listing_details.csv", "--workers", "4"]
