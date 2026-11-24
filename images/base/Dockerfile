# deliverbench base image: the starting point of every job's main room.
# Build context is images/base only (see .dockerignore), so no job's tests or solutions can enter it.
# Python 3.12.16 on Debian slim, pinned by digest; libraries pinned by hash in requirements.lock.
FROM python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

RUN apt-get update \
 && apt-get install -y --no-install-recommends bash curl git jq procps less \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

RUN useradd --create-home --uid 1000 --shell /bin/bash agent \
 && mkdir -p /app && chown agent:agent /app

ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
USER agent

LABEL org.opencontainers.image.title="deliverbench-base" \
      org.opencontainers.image.version="0.1.0"
