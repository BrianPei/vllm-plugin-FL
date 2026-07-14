#!/bin/bash
# Copyright (c) 2025 BAAI. All rights reserved.
# Setup script for MetaX C550 CI environment.
set -euo pipefail

git config --global --add safe.directory "$(pwd)"

export PATH="/opt/conda/bin:${PATH}"
export GEMS_VENDOR="${GEMS_VENDOR:-metax}"
export VLLM_PLUGINS="${VLLM_PLUGINS:-fl}"
export MACA_VISIBLE_DEVICES="${MACA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"

if [[ -n "${GITHUB_ENV:-}" ]]; then
  for name in \
    PATH \
    GEMS_VENDOR \
    VLLM_PLUGINS \
    MACA_VISIBLE_DEVICES; do
    echo "${name}=${!name}" >> "${GITHUB_ENV}"
  done
fi

python -m pip install --upgrade pip

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

python -m pip install "${TEST_DEPS[@]}"

VLLM_REF="${VLLM_REF:-v0.20.2}"
VLLM_SOURCE="${VLLM_SOURCE:-/workspace/vllm}"

python -m pip uninstall -y vllm || true
python -m pip cache remove vllm || true
SITE_PACKAGES="$(python -c "import site; print(site.getsitepackages()[0])")"
find "${SITE_PACKAGES}" -maxdepth 1 \
  \( -name "vllm" -o -name "vllm-*.dist-info" -o -name "vllm-*.egg-info" \) \
  -exec rm -rf {} + 2>/dev/null || true

if [[ ! -d "${VLLM_SOURCE}/.git" ]]; then
  rm -rf "${VLLM_SOURCE}"
  git clone https://github.com/vllm-project/vllm.git "${VLLM_SOURCE}"
fi
git config --global --add safe.directory "${VLLM_SOURCE}"
git -C "${VLLM_SOURCE}" fetch --tags --depth 1 origin "${VLLM_REF}" || true
git -C "${VLLM_SOURCE}" checkout "${VLLM_REF}"
VLLM_TARGET_DEVICE=empty python -m pip install -v --no-build-isolation -e "${VLLM_SOURCE}" --no-deps

python -m pip install --no-build-isolation --no-deps -e .

FLAGGEMS_REF="${FLAGGEMS_REF:-3123859968915e361e8452dd796dc6b27c956324}"
FLAGGEMS_SOURCE="${FLAGGEMS_PATH:-/workspace/FlagGems}"

if [[ ! -d "${FLAGGEMS_SOURCE}/.git" ]]; then
  rm -rf "${FLAGGEMS_SOURCE}"
  git clone https://github.com/FlagOpen/FlagGems.git "${FLAGGEMS_SOURCE}"
fi
git config --global --add safe.directory "${FLAGGEMS_SOURCE}"
git -C "${FLAGGEMS_SOURCE}" checkout "${FLAGGEMS_REF}"
python -m pip install -r "${FLAGGEMS_SOURCE}/requirements/requirements_metax.txt"
GEMS_VENDOR=metax python -m pip install -v -e "${FLAGGEMS_SOURCE}"

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
