#!/usr/bin/env python3
# Copyright (c) 2025 BAAI. All rights reserved.

"""Detect which platforms to test in CI.

Priority:
  1. If .github/configs/platforms.yml exists, read it and return only
     platforms with ``enabled: true``.
  2. Otherwise, fall back to auto-scanning .github/configs/*.yml,
     excluding ``template`` and ``platforms`` (the registry file itself).

Usage (in a workflow step)::

    - id: detect
      run: python3 .github/scripts/detect_platforms.py

Sets the GitHub Actions output ``platforms`` to a JSON array of platform
names, e.g. ``["cuda", "ascend"]``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / ".github" / "configs"
PLATFORMS_DIR = REPO_ROOT / "tests" / "platforms"
REGISTRY_FILE = CONFIGS_DIR / "platforms.yml"

# Names to exclude when falling back to auto-scan
AUTO_SCAN_EXCLUDE = {"template", "platforms"}


def from_registry() -> list[str] | None:
    """Read platforms.yml and return enabled platform names, or None if
    the file does not exist."""
    if not REGISTRY_FILE.exists():
        return None

    with open(REGISTRY_FILE) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "platforms" not in data:
        print(
            "::warning::platforms.yml exists but has no 'platforms' key",
            file=sys.stderr,
        )
        return []

    platforms = data["platforms"]
    if not isinstance(platforms, dict):
        print("::warning::platforms.yml 'platforms' is not a mapping", file=sys.stderr)
        return []

    enabled = [
        name
        for name, cfg in platforms.items()
        if isinstance(cfg, dict) and cfg.get("enabled", False)
    ]
    return enabled


def from_auto_scan() -> list[str]:
    """Scan .github/configs/*.yml and return platform names (minus exclusions)."""
    if not CONFIGS_DIR.is_dir():
        print(f"::error::Configs directory not found: {CONFIGS_DIR}", file=sys.stderr)
        return []

    return sorted(
        p.stem for p in CONFIGS_DIR.glob("*.yml") if p.stem not in AUTO_SCAN_EXCLUDE
    )


def set_output(name: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_OUTPUT (or print for local runs)."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{name}<<EOF\n{value}\nEOF\n")
    else:
        print(f"{name}={value}")


def load_changed_files(path: str) -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def platform_from_path(path: str) -> str | None:
    if path.startswith(".github/configs/"):
        name = Path(path).stem
        return None if name == "platforms" else name

    if path.startswith(".github/scripts/"):
        parts = path.split("/")
        return parts[2] if len(parts) > 3 else None

    if path.startswith("tests/platforms/"):
        name = Path(path).stem
        return None if name == "template" else name

    return None


def model_changes(changed_files: list[str]) -> tuple[set[str], set[tuple[str, str]]]:
    models: set[str] = set()
    cases: set[tuple[str, str]] = set()
    for path in changed_files:
        parts = path.split("/")
        if len(parts) >= 3:
            models.add(parts[2])
        if len(parts) == 4 and path.endswith(".yaml"):
            cases.add((parts[2], Path(parts[3]).stem))
    return models, cases


def platform_uses_model_change(
    platform: str,
    models: set[str],
    cases: set[tuple[str, str]],
) -> bool:
    path = PLATFORMS_DIR / f"{platform}.yaml"
    if not path.exists():
        return False

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    for section in config.values():
        e2e = (
            section.get("tests", {}).get("e2e", {})
            if isinstance(section, dict)
            else {}
        )
        for task_models in e2e.values():
            if not isinstance(task_models, dict):
                continue
            for model, task_cases in task_models.items():
                if model not in models:
                    continue
                if not cases:
                    return True
                if not isinstance(task_cases, list):
                    task_cases = [task_cases]
                if any((model, str(case)) in cases for case in task_cases):
                    return True
    return False


def detect_scoped_platforms(
    enabled_platforms: list[str],
    changed_files: list[str],
) -> list[str] | None:
    if not changed_files:
        return None

    platforms: set[str] = set()
    has_model_change = False
    for path in changed_files:
        if path == ".github/configs/platforms.yml":
            continue
        if path.startswith("tests/models/"):
            has_model_change = True
            continue

        platform = platform_from_path(path)
        if not platform:
            return None
        platforms.add(platform)

    if platforms:
        enabled = set(enabled_platforms)
        return [platform for platform in sorted(platforms) if platform in enabled]

    if has_model_change:
        models, cases = model_changes(changed_files)
        return [
            platform
            for platform in enabled_platforms
            if platform_uses_model_change(platform, models, cases)
        ]

    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect CI platforms to test")
    parser.add_argument("--changed-files", default=None)
    args = parser.parse_args(argv)

    platforms = from_registry()

    if platforms is not None:
        source = "platforms.yml"
    else:
        print(
            "::notice::platforms.yml not found, falling back to auto-scan",
            file=sys.stderr,
        )
        platforms = from_auto_scan()
        source = "auto-scan"

    if not platforms:
        print("::warning::No platforms detected", file=sys.stderr)

    if args.changed_files:
        changed_files = load_changed_files(args.changed_files)
        scoped_platforms = detect_scoped_platforms(
            platforms,
            changed_files,
        )
        if scoped_platforms is not None:
            platforms = scoped_platforms
            source = "changed-files"

    result = json.dumps(platforms)
    set_output("platforms", result)

    print(f"Source:     {source}")
    print(f"Platforms:  {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
