ARG METAX_BASE_IMAGE=harbor.baai.ac.cn/flagos-dev/vllm-plugin-fl:vllm-metax-0.20.0-maca.ai3.7.0.107-torch2.8-py312-ubuntu22.04-amd64

# ---------- base stage ----------
FROM ${METAX_BASE_IMAGE} AS base

ENV DEBIAN_FRONTEND=noninteractive

# actions/checkout needs git in the job container before any CI setup script runs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---------- dev stage ----------
FROM base AS dev

WORKDIR /workspace

# ---------- ci stage ----------
FROM base AS ci

WORKDIR /workspace

# ---------- release stage ----------
FROM base AS release

WORKDIR /workspace
