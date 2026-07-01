#!/bin/bash
# Copyright (c) 2025 BAAI. All rights reserved.
# Check Hygon DCU availability.
set -euo pipefail

echo "Current time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=== Checking Hygon DCU availability ==="

command -v hy-smi
hy-smi
hy-smi --showmeminfo vram || true

test -e /dev/kfd
test -e /dev/mkfd
test -d /dev/dri
test -d /opt/hyhal
