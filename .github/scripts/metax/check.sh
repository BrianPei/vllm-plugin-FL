#!/bin/bash
# Copyright (c) 2026 BAAI. All rights reserved.
# Check MetaX C550 device availability.
set -euo pipefail

echo "=== Checking MetaX C550 availability ==="

test -e /dev/mxcd
test -d /dev/dri

if command -v mx-smi >/dev/null 2>&1; then
  mx-smi
else
  echo "WARNING: mx-smi is unavailable; device files were detected."
fi

python - <<'PY'
import torch

assert torch.cuda.is_available(), "MetaX PyTorch reports no MACA devices"
count = torch.cuda.device_count()
assert count >= 4, f"MetaX E2E tests require at least 4 devices, found {count}"
print(f"MetaX devices visible to PyTorch: {count}")
PY
