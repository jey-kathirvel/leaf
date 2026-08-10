FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        postgresql \
        postgresql-contrib \
        libpq-dev \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

USER ubuntu
