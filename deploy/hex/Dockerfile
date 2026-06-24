# syntax=docker/dockerfile:1
#
# HEx image: builds the frontend, installs the backend, serves BOTH on one port
# (single origin). Build context is the repo root (see compose `build.context: ..`).
# TODO[pin]: pin base images + the uv image to @sha256 digests (NOTES.md).

# --- Stage 1: build the frontend SPA ---
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend runtime (serves API + built SPA) ---
FROM python:3.12-slim AS runtime
# uv provides reproducible, hash-locked installs. TODO[verify/pin] the uv image tag.
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

# Install dependencies against the frozen lockfile (no dev group in the image).
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Built SPA, served on the same origin via HEX_STATIC_DIR.
COPY --from=frontend /frontend/dist /app/frontend

ENV PATH="/app/.venv/bin:$PATH" \
    HEX_STATIC_DIR=/app/frontend

# Non-root runtime user (least privilege).
RUN useradd --system --uid 10001 --no-create-home hex \
    && chown -R hex:hex /app
USER hex

EXPOSE 8000
# hex.serve opens the proxy-facing socket plus (when break-glass is enabled) a separate
# LAN-bound socket; a single uvicorn process serves both (ADR 0008).
CMD ["python", "-m", "hex.serve"]
