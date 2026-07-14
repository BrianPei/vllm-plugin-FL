#!/bin/bash
# Copyright (c) 2025 BAAI. All rights reserved.
# Setup script for MetaX C550 CI environment.
set -euo pipefail

export PATH="/opt/conda/bin:${PATH}"
export GEMS_VENDOR="${GEMS_VENDOR:-metax}"
export VLLM_PLUGINS="${VLLM_PLUGINS:-fl}"
export MACA_VISIBLE_DEVICES="${MACA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
VLLM_SOURCE="${VLLM_SOURCE:-/workspace/vllm}"
FLAGGEMS_SOURCE="${FLAGGEMS_PATH:-/workspace/FlagGems}"

if [[ -n "${GITHUB_ENV:-}" ]]; then
  for name in \
    PATH \
    GEMS_VENDOR \
    VLLM_PLUGINS \
    MACA_VISIBLE_DEVICES; do
    echo "${name}=${!name}" >> "${GITHUB_ENV}"
  done
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
  sqlalchemy
)

echo "Using local vLLM source: ${VLLM_SOURCE}"
echo "Using local FlagGems source: ${FLAGGEMS_SOURCE}"
if [[ ! -f "${VLLM_SOURCE}/pyproject.toml" || ! -d "${VLLM_SOURCE}/vllm" ]]; then
  echo "Local vLLM source is missing or incomplete: ${VLLM_SOURCE}"
  exit 1
fi
if [[ ! -f "${FLAGGEMS_SOURCE}/pyproject.toml" \
  || ! -d "${FLAGGEMS_SOURCE}/src/flag_gems" \
  || ! -f "${FLAGGEMS_SOURCE}/requirements/requirements_metax.txt" ]]; then
  echo "Local FlagGems source is missing or incomplete: ${FLAGGEMS_SOURCE}"
  exit 1
fi

python -m pip uninstall -y vllm || true
python -m pip cache remove vllm || true
SITE_PACKAGES="$(python -c "import site; print(site.getsitepackages()[0])")"
find "${SITE_PACKAGES}" -maxdepth 1 \
  \( -name "vllm" -o -name "vllm-*.dist-info" -o -name "vllm-*.egg-info" \) \
  -exec rm -rf {} + 2>/dev/null || true

if command -v uv >/dev/null 2>&1; then
  uv pip install --system --upgrade pip
  uv pip install --system "${TEST_DEPS[@]}"
  VLLM_TARGET_DEVICE=empty uv pip install --system --no-build-isolation -e "${VLLM_SOURCE}" --no-deps
  uv pip install --system --no-build-isolation --no-deps -e .
else
  python -m pip install --upgrade pip
  python -m pip install "${TEST_DEPS[@]}"
  VLLM_TARGET_DEVICE=empty python -m pip install -v --no-build-isolation -e "${VLLM_SOURCE}" --no-deps
  python -m pip install --no-build-isolation --no-deps -e .
fi

FLAGGEMS_DIR="$(mktemp -d)/FlagGems"
cp -a "${FLAGGEMS_SOURCE}" "${FLAGGEMS_DIR}"

if command -v uv >/dev/null 2>&1; then
  uv pip install --system -r "${FLAGGEMS_DIR}/requirements/requirements_metax.txt"
  GEMS_VENDOR=metax uv pip install --system -e "${FLAGGEMS_DIR}"
else
  python -m pip install -r "${FLAGGEMS_DIR}/requirements/requirements_metax.txt"
  GEMS_VENDOR=metax python -m pip install -v -e "${FLAGGEMS_DIR}"
fi

python - <<'PY'
import flag_gems
import torch
import vllm
import vllm_fl

print(f"vLLM import ok: {vllm.__version__}")
print(f"vLLM-FL import ok: {vllm_fl.__file__}")
print(f"FlagGems import ok: {getattr(flag_gems, '__version__', 'unknown')}")
print(f"Torch import ok: {torch.__version__}")
print(f"Accelerator available: {torch.cuda.is_available()}")
print(f"Accelerator count: {torch.cuda.device_count()}")
PY
