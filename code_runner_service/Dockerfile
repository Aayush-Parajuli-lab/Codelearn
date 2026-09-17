# CodeLearn — code runner image
# Isolated from the main web app on purpose: this is the only container
# that ever executes untrusted student code. Hardened at the
# podman-compose.yml level (read-only rootfs, no outbound network,
# non-root, tight CPU/memory caps) rather than relying on the app code
# alone for isolation.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# gcc for C submissions, default-jdk-headless for Java submissions.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Non-root, and a writable tmp dir the container's read_only rootfs
# (set in podman-compose.yml via a tmpfs mount) provides at runtime.
# HOME=/tmp so gunicorn's control/state files land on the writable
# tmpfs mount instead of the (read-only) home directory.
ENV HOME=/tmp
RUN useradd --create-home --uid 1001 runner
USER runner

EXPOSE 6000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:6000", "--workers", "2", "--timeout", "30"]
