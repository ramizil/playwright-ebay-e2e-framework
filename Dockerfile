# =============================================================================
# Dockerfile — Containerised E2E Test Runner
# =============================================================================
# Multi-stage build that produces a lean image with Python 3.12, Playwright
# browsers, and the test framework pre-installed.
#
# Usage:
#   docker build -t ebay-e2e .
#   docker run --rm -v $(pwd)/allure-results:/app/allure-results ebay-e2e
#
# Environment variables (override at runtime):
#   EBAY_BROWSER   – chromium | firefox | webkit  (default: chromium)
#   EBAY_HEADLESS  – true | false                  (default: true)
#   EBAY_BASE_URL  – target site URL

FROM python:3.12-slim AS base

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies required by Playwright browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers + system deps
RUN python -m playwright install --with-deps chromium firefox

# Copy the framework code
COPY . .

# Create output directories
RUN mkdir -p allure-results screenshots traces logs reports

# Default environment
ENV EBAY_BROWSER=chromium
ENV EBAY_HEADLESS=true
ENV PYTHONUNBUFFERED=1

# Default command: run all E2E + smoke tests
CMD ["pytest", "tests/", "-v", "--alluredir=allure-results", "-n", "auto", "--dist=loadfile", "-m", "e2e or smoke"]
