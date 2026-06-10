#!/bin/bash
# Copyright (c) 2025 BAAI. All rights reserved.
# Check Hygon DCU availability.
set -euo pipefail

echo "=== Checking Hygon DCU availability ==="

command -v hy-smi
hy-smi
hy-smi --showmeminfo vram || true

test -e /dev/kfd
test -e /dev/mkfd
test -d /dev/dri
test -d /opt/hyhal
