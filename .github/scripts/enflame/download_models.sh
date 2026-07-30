#!/bin/bash
# Download the Enflame CI models into the shared host model hierarchy.
set -euo pipefail

MODEL_ROOT="${MODEL_ROOT:-/data/models/Qwen}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-120}"

export HF_ENDPOINT HF_HUB_DISABLE_XET HF_HUB_DOWNLOAD_TIMEOUT

if command -v hf >/dev/null 2>&1; then
  DOWNLOAD=(hf download)
elif command -v huggingface-cli >/dev/null 2>&1; then
  DOWNLOAD=(huggingface-cli download --resume-download)
else
  echo "Hugging Face CLI is required: python -m pip install -U huggingface_hub"
  exit 1
fi

mkdir -p "${MODEL_ROOT}"

"${DOWNLOAD[@]}" Qwen/Qwen3.6-27B \
  --local_dir "${MODEL_ROOT}/Qwen3.6-27B"

"${DOWNLOAD[@]}" Qwen/Qwen3.6-35B-A3B \
  --local_dir "${MODEL_ROOT}/Qwen3.6-35B-A3B"
