#!/bin/bash
# Copyright (c) 2025 BAAI. All rights reserved.
# Setup script for Hygon DCU CI environment.
set -euo pipefail

git config --global --add safe.directory "$(pwd)"

if command -v uv >/dev/null 2>&1; then
  uv pip install --system --upgrade pip
  uv pip install --system --no-build-isolation -e ".[test]"
else
  python -m pip install --upgrade pip
  python -m pip install --no-build-isolation -e ".[test]"
fi
