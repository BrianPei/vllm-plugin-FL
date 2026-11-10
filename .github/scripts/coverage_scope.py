#!/usr/bin/env python3
"""Create a platform-effective coverage.py JSON report.

The native coverage.py report remains the full-package baseline.  The
effective report applies the existing configured backend scope while retaining
all shared code, including platform-specific branches in shared modules such as
``vllm_fl/platform.py``. It does not infer ownership from test outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

DEFAULT_CONFIG = Path(".github/configs/coverage_scope.yml")
LINE_COUNTS = ("covered_lines", "num_statements", "missing_lines", "excluded_lines")
OPTIONAL_COUNTS = (
    ("covered_branches", "num_branches", "missing_branches"),
    ("covered_functions", "num_functions", "missing_functions"),
)


def _load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised by CI setup
        raise ValueError(
            "PyYAML is required to compute platform-effective coverage"
        ) from exc

    try:
        with path.open(encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
    except yaml.YAMLError as exc:
        raise ValueError("Invalid coverage scope YAML") from exc
    if not isinstance(config, dict):
        raise ValueError(f"Coverage scope config must be a mapping: {path}")
    return config


def _platform_scope(
    config: dict[str, Any], platform: str
) -> tuple[str | None, dict[str, Any]]:
    platforms = config.get("platforms")
    if not isinstance(platforms, dict) or platform not in platforms:
        known = (
            ", ".join(sorted(map(str, platforms)))
            if isinstance(platforms, dict)
            else ""
        )
        raise ValueError(
            f"Unknown coverage platform {platform!r}; configured platforms: {known}"
        )
    entry = platforms[platform]
    if not isinstance(entry, dict):
        raise ValueError(f"Coverage platform {platform!r} has no mapping")
    backend = entry.get("backend")
    mode = entry.get("mode", "backend_plus_shared")
    if mode not in ("shared_only", "backend_plus_shared"):
        raise ValueError(f"Invalid coverage mode for {platform!r}: {mode!r}")
    if backend is not None and (
        not isinstance(backend, str)
        or not backend
        or "/" in backend
        or "\\" in backend
        or backend in (".", "..")
    ):
        raise ValueError(f"Invalid backend mapping for {platform!r}")
    if backend is None and mode != "shared_only":
        raise ValueError(f"Coverage platform {platform!r} has no backend mapping")
    selected_backend = None if mode == "shared_only" else backend
    return selected_backend, entry


def _relative_root(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    if (
        PureWindowsPath(normalized).drive
        or normalized.startswith("/")
        or ".." in normalized.split("/")
    ):
        raise ValueError(f"{label} must be a relative path without '..'")
    normalized = str(PurePosixPath(normalized))
    if normalized == ".":
        raise ValueError(f"{label} must name a directory")
    return normalized


def _package_path(path: str, package_root: str) -> str:
    """Accept package-relative or absolute CI paths, never outside-package files."""
    if (
        not isinstance(path, str)
        or not path
        or ".." in path.replace("\\", "/").split("/")
    ):
        raise ValueError("Invalid coverage file path")
    normalized = str(PurePosixPath(path.replace("\\", "/")))
    absolute = normalized.startswith("/") or PureWindowsPath(normalized).is_absolute()
    if absolute:
        marker = f"/{package_root}/"
        if normalized.count(marker) != 1:
            raise ValueError(f"File outside package_root or ambiguous path: {path}")
        normalized = package_root + "/" + normalized.split(marker, 1)[1]
    if not normalized.startswith(package_root + "/"):
        raise ValueError(f"File outside package_root: {path}")
    return normalized


def _validate_summary(summary: Any, label: str) -> None:
    if not isinstance(summary, dict):
        raise ValueError(f"{label}: missing or invalid summary")
    keys = list(LINE_COUNTS)
    for group in OPTIONAL_COUNTS:
        if any(key in summary for key in group):
            keys.extend(group)
    if "num_partial_branches" in summary:
        keys.append("num_partial_branches")
    for key in keys:
        if type(summary.get(key)) is not int or summary[key] < 0:
            raise ValueError(f"{label}: {key} must be a non-negative integer")
    for covered, total, missing in (LINE_COUNTS[:3], *OPTIONAL_COUNTS):
        if total in summary and summary[covered] + summary[missing] != summary[total]:
            raise ValueError(f"{label}: {covered} + {missing} must equal {total}")
    if summary.get("num_partial_branches", 0) > summary.get("missing_branches", 0):
        raise ValueError(f"{label}: partial branches exceed missing branches")
    percent = summary.get("percent_covered")
    if (
        type(percent) not in (int, float)
        or not math.isfinite(percent)
        or not 0 <= percent <= 100
    ):
        raise ValueError(
            f"{label}: percent_covered must be finite and between 0 and 100"
        )
    denominator = summary["num_statements"] + summary.get("num_branches", 0)
    numerator = summary["covered_lines"] + summary.get("covered_branches", 0)
    if denominator and not math.isclose(
        percent, 100 * numerator / denominator, abs_tol=1e-6
    ):
        raise ValueError(f"{label}: percent_covered is inconsistent with counts")


def _validate_report(report: Any, package_root: str) -> dict[str, str]:
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise ValueError("Not a coverage.py JSON report: files must be a mapping")
    meta = report.get("meta")
    if not isinstance(meta, dict) or type(meta.get("branch_coverage")) is not bool:
        raise ValueError("Missing or invalid meta.branch_coverage")
    normalized_paths = {}
    seen = set()
    for path, data in report["files"].items():
        normalized = _package_path(path, package_root)
        if normalized in seen:
            raise ValueError(
                f"Duplicate coverage file after path normalization: {path}"
            )
        seen.add(normalized)
        normalized_paths[path] = normalized
        if not isinstance(data, dict):
            raise ValueError(f"{path}: file data must be a mapping")
        _validate_summary(data.get("summary"), path)
        if meta["branch_coverage"] and "num_branches" not in data["summary"]:
            raise ValueError(f"{path}: branch coverage counts are missing")
        for key in ("executed_lines", "missing_lines", "excluded_lines"):
            lines = data.get(key)
            if (
                not isinstance(lines, list)
                or any(type(line) is not int or line < 0 for line in lines)
                or len(set(lines)) != len(lines)
            ):
                raise ValueError(f"{path}: {key} must be a list of unique line numbers")
            if key != "executed_lines" and len(lines) != data["summary"][key]:
                raise ValueError(f"{path}: {key} count does not match its summary")
        # Executed lines can include excluded/non-statement lines in coverage.py.
        # Do not equate their length with covered executable statements.
        if set(data["missing_lines"]) & (
            set(data["executed_lines"]) | set(data["excluded_lines"])
        ):
            raise ValueError(
                f"{path}: missing lines overlap executed or excluded lines"
            )
        if data["summary"]["covered_lines"] > len(
            set(data["executed_lines"]) - set(data["excluded_lines"])
        ):
            raise ValueError(f"{path}: covered_lines exceeds executed line count")
    _validate_summary(report.get("totals"), "totals")
    expected = _sum_totals(report["files"])
    count_keys = set(LINE_COUNTS)
    for group in OPTIONAL_COUNTS:
        if any(key in expected or key in report["totals"] for key in group):
            count_keys.update(group)
    if "num_partial_branches" in expected or "num_partial_branches" in report["totals"]:
        count_keys.add("num_partial_branches")
    for key in count_keys:
        if report["totals"].get(key) != expected.get(key, 0):
            raise ValueError(f"totals: {key} does not equal the sum of file summaries")
    return normalized_paths


def _vendor_name(path: str, vendor_root: str) -> str | None:
    normalized = path.replace("\\", "/")
    marker = f"/{vendor_root.strip('/')}/"
    rooted = f"/{normalized.lstrip('/')}"
    if marker not in rooted:
        return None

    suffix = rooted.split(marker, 1)[1]
    name = suffix.split("/", 1)[0]
    # The package __init__.py belongs to shared dispatch scaffolding.  It is
    # not an implementation directory and remains in every denominator.
    return None if "/" not in suffix else name


def _sum_totals(files: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, Any] = dict.fromkeys(LINE_COUNTS, 0)
    for file_data in files.values():
        summary = file_data.get("summary")
        _validate_summary(summary, "file")
        for key in (
            "covered_lines",
            "num_statements",
            "missing_lines",
            "excluded_lines",
            "covered_branches",
            "num_branches",
            "missing_branches",
            "num_partial_branches",
            "covered_functions",
            "num_functions",
            "missing_functions",
        ):
            if key in summary:
                totals[key] = totals.get(key, 0) + summary[key]

    statements = totals.get("num_statements", 0)
    covered_lines = totals.get("covered_lines", 0)
    percent = 100.0 * covered_lines / statements if statements else None
    totals["percent_covered"] = percent
    totals["percent_covered_display"] = (
        f"{percent:.0f}" if percent is not None else "N/A"
    )

    branches = totals.get("num_branches", 0)
    if branches:
        branch_percent = 100.0 * totals.get("covered_branches", 0) / branches
        totals["percent_covered_branches"] = branch_percent
        totals["percent_covered_branches_display"] = f"{branch_percent:.0f}"

    functions = totals.get("num_functions", 0)
    if functions:
        function_percent = 100.0 * totals.get("covered_functions", 0) / functions
        totals["percent_covered_functions"] = function_percent
        totals["percent_covered_functions_display"] = f"{function_percent:.0f}"

    return totals


def _copy_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant: {value}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--scope", default="unknown")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--full-output", type=Path, required=True)
    parser.add_argument("--effective-output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-sha", required=True)
    statuses = ("success", "failure", "skipped", "cancelled", "unknown")
    parser.add_argument("--unit-status", choices=statuses, default="unknown")
    parser.add_argument("--functional-status", choices=statuses, default="unknown")
    return parser.parse_args()


def _effective_report(
    args: argparse.Namespace, metadata: dict[str, Any]
) -> dict[str, Any]:
    config = _load_config(args.config)
    package_root = _relative_root(config.get("package_root"), "package_root")
    vendor_root = _relative_root(config.get("vendor_root"), "vendor_root")
    if not vendor_root.startswith(package_root + "/"):
        raise ValueError("vendor_root must be inside package_root")
    backend, platform_scope = _platform_scope(config, args.platform.lower())
    metadata.update(
        {
            "package_root": package_root,
            "vendor_root": vendor_root,
            "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
            "runtime_backend": platform_scope.get("backend"),
            "resolved_backend": backend,
            "runtime_alias": platform_scope.get("runtime_alias"),
            "scope_mode": platform_scope.get("mode", "backend_plus_shared"),
            "notes": platform_scope.get("notes"),
        }
    )

    with args.input.open(encoding="utf-8") as stream:
        full_report = json.load(
            stream, object_pairs_hook=_json_object, parse_constant=_invalid_constant
        )
    paths = _validate_report(full_report, package_root)

    full_files = full_report["files"]
    selected_files: dict[str, Any] = {}
    excluded: dict[str, dict[str, int]] = {}
    for path, file_data in full_files.items():
        vendor = _vendor_name(paths[path], vendor_root)
        if vendor is None or vendor == backend:
            selected_files[path] = file_data
            continue

        summary = file_data.get("summary", {})
        bucket = excluded.setdefault(
            vendor,
            {"files": 0, "num_statements": 0, "covered_lines": 0, "missing_lines": 0},
        )
        bucket["files"] += 1
        for key in ("num_statements", "covered_lines", "missing_lines"):
            bucket[key] += int(summary.get(key, 0))

    effective_report = dict(full_report)
    effective_report["files"] = selected_files
    effective_report["totals"] = _sum_totals(selected_files)

    metadata.update(
        {
            # This is the only authoritative total for the platform metric.  The
            # full-package baseline is retained as a separate JSON artifact.
            "totals": effective_report["totals"],
            "excluded_vendor_directories": excluded,
            "scope_rule": (
                f"all {package_root} files plus the selected backend directory; "
                "other vendor directories are excluded"
                if backend
                else f"all {package_root} files except vendor backend directories"
            ),
        }
    )
    return effective_report


def main() -> None:
    args = _parse_args()
    # Never overwrite the raw input or another evidence file (including on failure).
    paths = [args.input, args.full_output, args.effective_output, args.metadata_output]
    if len({path.resolve() for path in paths}) != len(paths):
        raise SystemExit("Input, Full, Effective and metadata paths must be distinct")
    metadata = {
        "schema_version": "flagos.coverage.scope/v1",
        "platform": args.platform.lower(),
        "scope": args.scope,
        "source_sha": args.source_sha,
        "test_status": {"unit": args.unit_status, "functional": args.functional_status},
        "metric": "python_statement_coverage",
        "input_report": str(args.input),
        "status": "invalid_input",
        "upload_allowed": False,
    }
    try:
        args.full_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.input, args.full_output)
        report = _effective_report(args, metadata)
        metadata["status"] = (
            "ok" if report["totals"]["num_statements"] else "empty_scope"
        )
        metadata["upload_allowed"] = metadata["status"] == "ok"
    except (ValueError, OSError) as exc:
        metadata["error"] = str(exc)
        if not args.input.is_file():
            metadata["status"] = "missing_input"
            # No original report exists. Replace any stale Full output with an
            # explicit diagnostic marker, never a fabricated coverage report.
            _copy_json(
                {"status": "missing_input", "input_report": str(args.input)},
                args.full_output,
            )
        report = {"status": metadata["status"], "files": {}, "totals": None}
    # Failure outputs are diagnostic artifacts, never uploadable coverage metrics.
    _copy_json(report, args.effective_output)
    _copy_json(metadata, args.metadata_output)
    if not metadata["upload_allowed"]:
        raise SystemExit(
            f"[coverage] {metadata['status']}: upload blocked; see scope metadata"
        )
    print(
        f"[coverage] {args.platform}: effective={report['totals']['percent_covered']:.2f}%"
    )


if __name__ == "__main__":
    main()
