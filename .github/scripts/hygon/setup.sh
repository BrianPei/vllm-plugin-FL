#!/bin/bash
# Copyright (c) 2025 BAAI. All rights reserved.
# Setup script for Hygon DCU CI environment.
set -euo pipefail

git config --global --add safe.directory "$(pwd)"

mapfile -t HYGON_LIB_DIRS < <(
  {
    find -L /opt/hyhal /usr/local/hyhal -name "libgalaxyhip.so*" \
      -exec dirname {} \; 2>/dev/null || true
    for dir in \
      /opt/hyhal/lib \
      /opt/hyhal/lib64 \
      /opt/hyhal/hip/lib \
      /opt/hyhal/hip/lib64 \
      /opt/hyhal/lib/x86_64-linux-gnu \
      /usr/local/hyhal/lib \
      /usr/local/hyhal/lib64 \
      /usr/local/hyhal/hip/lib \
      /usr/local/hyhal/hip/lib64 \
      /usr/local/hyhal/lib/x86_64-linux-gnu; do
      [[ -d "${dir}" ]] && echo "${dir}"
    done
  } | awk '!seen[$0]++'
)

if [[ "${#HYGON_LIB_DIRS[@]}" -gt 0 ]]; then
  HYGON_LD_LIBRARY_PATH="$(IFS=:; echo "${HYGON_LIB_DIRS[*]}")"
  export LD_LIBRARY_PATH="${HYGON_LD_LIBRARY_PATH}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH}" >> "${GITHUB_ENV}"
  fi
  if command -v ldconfig >/dev/null 2>&1 && [[ -w /etc/ld.so.conf.d ]]; then
    printf "%s\n" "${HYGON_LIB_DIRS[@]}" > /etc/ld.so.conf.d/hygon.conf
    ldconfig
  fi
  echo "Configured Hygon LD_LIBRARY_PATH=${LD_LIBRARY_PATH}"
else
  echo "::warning::No Hygon library directories found under /opt/hyhal."
fi

TEST_DEPS=(
  pytest
  pytest-cov
  pytest-timeout
  pytest-json-report
  numpy
  requests
  openai
  decorator
  pyyaml
)

if command -v uv >/dev/null 2>&1; then
  uv pip install --system --upgrade pip
  uv pip install --system --no-build-isolation -e . --no-deps
  uv pip install --system "${TEST_DEPS[@]}"
else
  python -m pip install --upgrade pip
  python -m pip install --no-build-isolation -e . --no-deps
  python -m pip install "${TEST_DEPS[@]}"
fi

python - <<'PY'
import torch

print(f"Torch import ok: {torch.__version__}")
PY
