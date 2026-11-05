#!/bin/bash
set -euo pipefail
: "${FLAGCX_SOURCE_SHA:=d1cf5cb9ae375198437a98622573443b363b1c44}"
: "${MAX_JOBS:=8}"
export MAX_JOBS
export FLAGCX_ADAPTOR=du
export DEVICE_HOME=/opt/dtk/cuda/cuda-12 CCL_HOME=/opt/dtk/cuda/cuda-12 CUDA_PATH=/opt/dtk/cuda/cuda-12
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_FLAGCX=0.14.0+dtk2604.torch2100
mkdir -p /opt/src/flagcx /opt/release/flagcx-wheels
git -C /opt/src/flagcx init
git -C /opt/src/flagcx fetch --depth 1 https://github.com/flagos-ai/FlagCX.git "$FLAGCX_SOURCE_SHA"
git -C /opt/src/flagcx reset --hard FETCH_HEAD
test "$(git -C /opt/src/flagcx rev-parse HEAD)" = "$FLAGCX_SOURCE_SHA"
git -C /opt/src/flagcx submodule update --init --recursive
# Only bound build parallelism; communication and extension code are unchanged.
python - <<'PY'
from pathlib import Path
p=Path('/opt/src/flagcx/setup.py');s=p.read_text();old='str(multiprocessing.cpu_count())'
assert s.count(old)==1
p.write_text(s.replace(old,'str(int(os.environ.get("MAX_JOBS", "8")))'))
PY
python -m pip wheel --no-deps --no-build-isolation --wheel-dir /opt/release/flagcx-wheels /opt/src/flagcx
git -C /opt/src/flagcx diff -- setup.py > /opt/release/flagcx-wheels/build-parallelism.patch
printf '%s\n' "$FLAGCX_SOURCE_SHA" > /opt/release/flagcx-wheels/source-sha.txt
python -c 'from importlib.metadata import version; print(version("torch"))' > /opt/release/flagcx-wheels/build-torch-version.txt
sha256sum /opt/release/flagcx-wheels/*.whl > /opt/release/flagcx-wheels/wheel-sha256.txt
