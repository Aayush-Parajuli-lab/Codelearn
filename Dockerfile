# CodeLearn — web application image
# Runs Django via gunicorn. Includes gcc + a JDK so student C/Java
# submissions can compile & run even if the separate code-runner service
# (see code_runner_service/Dockerfile) isn't wired up — see
# code_runner/sandbox.py for how CODE_RUNNER_URL toggles between the two.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=codelearn.settings

WORKDIR /app

# System deps:
#   - default-libmysqlclient-dev + pkg-config + gcc/build-essential: for mysqlclient and C submissions
#   - default-jdk-headless: for Java submissions (javac + java)
#   - gosu: lets the entrypoint start as root (to fix ownership of
#     volume-mounted directories, which Podman/Docker mount as root-owned
#     regardless of what the image's build-time chown set), then drop
#     privileges to the unprivileged `codelearn` user before exec'ing
#     the actual server process.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
        default-jdk-headless \
        curl \
        gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 codelearn \
    && mkdir -p /app/staticfiles /app/media /app/ml_models \
    && chmod +x /app/docker/entrypoint.sh /app/docker/scheduler_loop.sh \
    && chown -R codelearn:codelearn /app

# Stay root here — the entrypoint fixes up ownership of volume mounts
# (which override the chown above at runtime) and then drops to
# `codelearn` itself via gosu before exec'ing gunicorn. See docker/entrypoint.sh.

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "codelearn.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
