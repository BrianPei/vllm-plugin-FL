# Copyright (c) 2026 BAAI. All rights reserved.

"""Format vllm bench serve metrics for FlagCICD benchmark reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _latency_metric(
    data: dict[str, Any],
    mean_key: str,
    median_key: str,
    p99_key: str,
) -> dict[str, Any]:
    avg = _num(data.get(mean_key))
    return {
        "values": [avg],
        "avg": avg,
        "p50": _num(data.get(median_key)),
        "p99": _num(data.get(p99_key)),
    }


def _throughput_metric(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = _num(data.get(key))
    return {
        "values": [value],
        "avg": value,
        "p50": value,
        "p99": value,
    }


def build_report(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ttft_ms": _latency_metric(
            data, "mean_ttft_ms", "median_ttft_ms", "p99_ttft_ms"
        ),
        "tpot_ms": _latency_metric(
            data, "mean_tpot_ms", "median_tpot_ms", "p99_tpot_ms"
        ),
        "itl_ms": _latency_metric(data, "mean_itl_ms", "median_itl_ms", "p99_itl_ms"),
        "e2el_ms": _latency_metric(
            data, "mean_e2el_ms", "median_e2el_ms", "p99_e2el_ms"
        ),
        "request_throughput_req_s": _throughput_metric(data, "request_throughput"),
        "request_goodput_req_s": _throughput_metric(data, "request_goodput"),
        "output_throughput_tok_s": _throughput_metric(data, "output_throughput"),
        "total_token_throughput_tok_s": _throughput_metric(
            data, "total_token_throughput"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    report = build_report(data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
