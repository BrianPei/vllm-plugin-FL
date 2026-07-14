#!/bin/bash
# Copyright (c) 2026 BAAI. All rights reserved.
# Prepare the vLLM empty + FlagGems stack for MetaX CI.
set -euo pipefail

VLLM_VERSION="v0.20.2"
FLAGGEMS_COMMIT="3123859968915e361e8452dd796dc6b27c956324"
VLLM_SRC="/tmp/vllm-${VLLM_VERSION}"
FLAGGEMS_SRC="/tmp/FlagGems-${FLAGGEMS_COMMIT}"
FLAGGEMS_ARCHIVE="${FLAGGEMS_SRC}.tar.gz"
PYTHON="${PYTHON:-/opt/conda/bin/python}"

if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git
fi

git config --global --add safe.directory "$(pwd)"

export GEMS_VENDOR=metax
export VLLM_PLUGINS=fl
export VLLM_TARGET_DEVICE=empty

for path in "${VLLM_SRC}" "${FLAGGEMS_SRC}"; do
  case "$(readlink -m "${path}")" in
    /tmp/vllm-v0.20.2 | /tmp/FlagGems-${FLAGGEMS_COMMIT}) ;;
    *) echo "Unsafe temporary path: ${path}" >&2; exit 1 ;;
  esac
  rm -rf -- "${path}"
done
rm -f -- "${FLAGGEMS_ARCHIVE}"

git -c http.version=HTTP/1.1 clone --depth 1 --branch "${VLLM_VERSION}" \
  https://github.com/vllm-project/vllm.git "${VLLM_SRC}"
VLLM_TARGET_DEVICE=empty "${PYTHON}" -m pip install \
  --no-build-isolation --no-deps -e "${VLLM_SRC}"

curl --fail --location \
  --retry 5 --retry-all-errors --retry-delay 5 \
  --connect-timeout 30 --max-time 600 \
  "https://codeload.github.com/FlagOpen/FlagGems/tar.gz/${FLAGGEMS_COMMIT}" \
  --output "${FLAGGEMS_ARCHIVE}"
mkdir -p "${FLAGGEMS_SRC}"
tar -xzf "${FLAGGEMS_ARCHIVE}" --strip-components=1 -C "${FLAGGEMS_SRC}"
printf '%s\n' "${FLAGGEMS_COMMIT}" > "${FLAGGEMS_SRC}/.source_commit"
"${PYTHON}" -m pip install \
  -r "${FLAGGEMS_SRC}/requirements/requirements_metax.txt"
"${PYTHON}" -m pip install \
  "numpy==1.26.4" \
  "outlines-core==0.2.14" \
  "packaging==26.0" \
  "PyYAML==6.0.3" \
  "sqlalchemy==2.0.48"
GEMS_VENDOR=metax "${PYTHON}" -m pip install \
  -v --no-build-isolation --no-deps -e "${FLAGGEMS_SRC}"

# Do not set VLLM_VENDOR here. The validated empty-vLLM setup installs the
# plugin without its optional CUDA extension and uses FlagGems for operators.
"${PYTHON}" -m pip install \
  --no-build-isolation --no-deps -e .
"${PYTHON}" -m pip install \
  pytest pytest-cov pytest-timeout pytest-json-report \
  requests openai decorator "modelscope>=1.18.1"

"${PYTHON}" - <<'PY'
from importlib.metadata import version

import flag_gems
import vllm_fl

assert version("vllm").startswith("0.20.2+empty"), version("vllm")
assert version("flag-gems") == "5.0.2", version("flag-gems")
print(f"vLLM: {version('vllm')}")
print(f"vllm-plugin-FL: {vllm_fl.__file__}")
print(f"FlagGems: {version('flag-gems')}")
PY
