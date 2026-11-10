"""CPU-only regression tests; no imports of vllm_fl, torch or GPU fixtures."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/coverage_scope.py"
CONFIG = ROOT / ".github/configs/coverage_scope.yml"
SPEC = importlib.util.spec_from_file_location("coverage_scope", SCRIPT)
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)
SHA = "eaf6ad9c60ab53b85bf95d19e229f17646838aa9"


def file_data(covered, missing, excluded=()):
    return {
        "executed_lines": covered,
        "missing_lines": missing,
        "excluded_lines": list(excluded),
        "summary": {
            "covered_lines": len(covered),
            "num_statements": len(covered) + len(missing),
            "missing_lines": len(missing),
            "excluded_lines": len(excluded),
            "percent_covered": 100 * len(covered) / (len(covered) + len(missing))
            if covered or missing
            else 100,
        },
    }


def report(files):
    totals = {
        key: sum(data["summary"][key] for data in files.values())
        for key in (
            "covered_lines",
            "num_statements",
            "missing_lines",
            "excluded_lines",
        )
    }
    totals["percent_covered"] = (
        100 * totals["covered_lines"] / totals["num_statements"]
        if totals["num_statements"]
        else 100
    )
    return {
        "meta": {"version": "7.17.2", "branch_coverage": False},
        "files": files,
        "totals": totals,
    }


@pytest.fixture
def sample():
    return report(
        {
            "vllm_fl/utils.py": file_data([1], [2], [3]),
            "vllm_fl/dispatch/backends/vendor/__init__.py": file_data([1], []),
            "vllm_fl/dispatch/backends/vendor/cuda/a.py": file_data([1, 2, 3], [4]),
            "vllm_fl/dispatch/backends/vendor/ascend/a.py": file_data([1], [2, 3]),
        }
    )


def invoke(tmp_path, payload, platform="nvidia", extra=()):
    original = tmp_path / "input.json"
    original.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    paths = {
        name: tmp_path / f"{name}.json" for name in ("full", "effective", "metadata")
    }
    args = [
        sys.executable,
        "-B",
        str(SCRIPT),
        "--platform",
        platform,
        "--config",
        str(CONFIG),
        "--source-sha",
        SHA,
        "--scope",
        "unit,functional",
        "--unit-status",
        "failure",
        "--functional-status",
        "skipped",
        "--input",
        str(original),
    ]
    for name, path in paths.items():
        args += [f"--{name}-output", str(path)]
    proc = subprocess.run([*args, *extra], cwd=ROOT, capture_output=True, text=True)
    assert paths["full"].read_bytes() == original.read_bytes()
    return proc, {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in paths.items()
        if name != "full"
    }


def test_full_effective_shared_owned_excluded_and_missing(tmp_path, sample):
    before = copy.deepcopy(sample)
    proc, outputs = invoke(tmp_path, sample)
    assert proc.returncode == 0, proc.stderr
    assert json.loads((tmp_path / "full.json").read_text()) == before
    effective, metadata = outputs["effective"], outputs["metadata"]
    assert effective["totals"]["covered_lines"] == 5
    assert effective["totals"]["num_statements"] == 7
    assert effective["totals"]["missing_lines"] == 2  # applicable gaps remain
    assert effective["totals"]["excluded_lines"] == 1  # pragma exclusions, not vendors
    assert effective["totals"]["percent_covered"] == pytest.approx(500 / 7)
    assert len(effective["files"]) == 3
    assert "vllm_fl/utils.py" in effective["files"]
    assert metadata["excluded_vendor_directories"] == {
        "ascend": {
            "files": 1,
            "num_statements": 3,
            "covered_lines": 1,
            "missing_lines": 2,
        }
    }
    assert metadata["source_sha"] == SHA
    assert metadata["test_status"] == {"unit": "failure", "functional": "skipped"}
    assert metadata["status"] == "ok" and metadata["upload_allowed"] is True
    assert metadata["package_root"] == "vllm_fl"
    assert len(metadata["config_sha256"]) == 64


@pytest.mark.parametrize(
    "platform,covered,total",
    [("nvidia", 5, 7), ("ascend", 3, 6), ("hygon", 2, 3), ("amd", 2, 3)],
)
def test_existing_platform_rules_not_redefined(
    tmp_path, sample, platform, covered, total
):
    proc, outputs = invoke(tmp_path, sample, platform)
    assert proc.returncode == 0
    assert outputs["effective"]["totals"]["covered_lines"] == covered
    assert outputs["effective"]["totals"]["num_statements"] == total
    assert outputs["effective"]["totals"]["percent_covered"] == pytest.approx(
        100 * covered / total
    )


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"vllm_fl/empty.py": file_data([], [])},
        {"vllm_fl/dispatch/backends/vendor/ascend/a.py": file_data([1], [2])},
    ],
)
def test_legal_empty_scope_is_not_corrupt_or_uploadable(tmp_path, files):
    proc, outputs = invoke(tmp_path, report(files))
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "empty_scope"
    assert outputs["metadata"]["upload_allowed"] is False
    assert outputs["effective"]["totals"]["num_statements"] == 0
    assert outputs["effective"]["totals"]["percent_covered"] is None
    assert outputs["effective"]["totals"]["percent_covered_display"] == "N/A"


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        '{"files":{}}',
        '{"files":{},"files":{}}',
        '{"meta":NaN}',
        '{"meta":Infinity}',
    ],
)
def test_invalid_json_preserves_raw_and_diagnostic_evidence(tmp_path, payload):
    proc, outputs = invoke(tmp_path, payload)
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "invalid_input"
    assert outputs["metadata"]["upload_allowed"] is False
    assert outputs["effective"]["totals"] is None
    assert outputs["metadata"]["error"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("covered_lines", 9),
        ("covered_lines", -1),
        ("num_statements", "2"),
        ("missing_lines", 1.5),
        ("excluded_lines", True),
        ("percent_covered", "50"),
        ("percent_covered", 101),
        ("percent_covered", 0),
    ],
)
def test_invalid_summary_counts_fail_closed(tmp_path, field, value):
    payload = report({"vllm_fl/a.py": file_data([1], [2])})
    payload["files"]["vllm_fl/a.py"]["summary"][field] = value
    proc, outputs = invoke(tmp_path, payload)
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "invalid_input"
    assert outputs["metadata"]["upload_allowed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "summary_missing",
        "summary_null",
        "field_missing",
        "file_null",
        "totals_mismatch",
        "line_count",
        "duplicate_lines",
        "missing_executed_overlap",
        "missing_meta",
    ],
)
def test_incomplete_or_inconsistent_report(tmp_path, mutation):
    payload = report({"vllm_fl/a.py": file_data([1], [2])})
    data = payload["files"]["vllm_fl/a.py"]
    if mutation == "summary_missing":
        del data["summary"]
    elif mutation == "summary_null":
        data["summary"] = None
    elif mutation == "field_missing":
        del data["summary"]["missing_lines"]
    elif mutation == "file_null":
        payload["files"]["vllm_fl/a.py"] = None
    elif mutation == "totals_mismatch":
        payload["totals"] = file_data([1, 2], [3, 4])["summary"]
    elif mutation == "line_count":
        data["missing_lines"] = []
    elif mutation == "duplicate_lines":
        data["executed_lines"] = [1, 1]
    elif mutation == "missing_executed_overlap":
        data["missing_lines"] = [1]
    else:
        del payload["meta"]
    proc, outputs = invoke(tmp_path, payload)
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "invalid_input"


@pytest.mark.parametrize(
    "prefix", ["", "./", "/home/runner/work/repo/", "C:\\work\\repo\\"]
)
def test_linux_and_windows_paths(tmp_path, prefix):
    path = prefix + "vllm_fl/dispatch/backends/vendor/cuda/a.py"
    if prefix.startswith("C:"):
        path = path.replace("/", "\\")
    proc, outputs = invoke(tmp_path, report({path: file_data([1], [2])}))
    assert proc.returncode == 0
    assert outputs["effective"]["totals"]["percent_covered"] == 50


@pytest.mark.parametrize(
    "path",
    [
        "outside/a.py",
        "vllm_fl_other/a.py",
        "vllm_fl/../outside/a.py",
        "/tmp/outside/a.py",
        "C:\\repo\\outside\\a.py",
        "other/vllm_fl/a.py",
    ],
)
def test_outside_package_is_error_not_shared(tmp_path, path):
    proc, outputs = invoke(tmp_path, report({path: file_data([1], [])}))
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "invalid_input"
    assert outputs["effective"]["totals"] is None


def test_unknown_platform(tmp_path, sample):
    proc, outputs = invoke(tmp_path, sample, "unknown")
    assert proc.returncode != 0
    assert "Unknown coverage platform" in outputs["metadata"]["error"]


def test_weighted_counts_not_average_percentages():
    totals = scope._sum_totals(
        {"a": file_data([1], [2]), "b": file_data(list(range(1, 10)), [10])}
    )
    assert totals["covered_lines"] == 10
    assert totals["num_statements"] == 12
    assert totals["percent_covered"] == pytest.approx(1000 / 12)
    assert totals["percent_covered"] != 70


def test_all_configured_backends_and_ci_platforms():
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ci = yaml.safe_load(
        (ROOT / ".github/configs/platforms.yml").read_text(encoding="utf-8")
    )
    expected = {
        "nvidia": "cuda",
        "ascend": "ascend",
        "hygon": None,
        "amd": None,
        "metax": "metax",
        "maca": "metax",
        "musa": "musa",
        "mthreads": "musa",
        "enflame": "gcu",
        "gcu": "gcu",
        "kunlunxin": "kunlunxin",
        "thead": "thead",
        "iluvatar": "iluvatar",
        "biren": "supa",
        "sunrise": "sunrise",
        "tsingmicro": "txda",
    }
    assert {
        p: scope._platform_scope(config, p)[0] for p in config["platforms"]
    } == expected
    assert set(ci["platforms"]) <= set(expected)


@pytest.mark.parametrize(
    "flags,covered,branches", [((True,), 3, 1), ((True, False), 4, 2)]
)
def test_real_coverage_json_with_branches_exclusions_and_append(
    tmp_path, monkeypatch, flags, covered, branches
):
    # Run actual coverage.py on a tiny CPU-only package, not on the GPU project.
    import coverage

    package = tmp_path / "vllm_fl"
    package.mkdir()
    monkeypatch.chdir(tmp_path)
    source = package / "sample.py"
    source.write_text(
        "def f(flag):\n    if flag:\n        return 1\n    return 2\n"
        "def ignored():  # pragma: no cover\n    return 3\n",
        encoding="utf-8",
    )
    data_file = tmp_path / ".coverage"
    for flag in flags:
        cov = coverage.Coverage(
            data_file=str(data_file),
            source=[str(package)],
            branch=True,
            config_file=False,
        )
        if data_file.exists():
            cov.load()
        cov.start()
        namespace = {}
        exec(compile(source.read_text(), str(source), "exec"), namespace)
        namespace["f"](flag)
        namespace["ignored"]()
        cov.stop()
        cov.save()
    raw = tmp_path / "real.json"
    cov.json_report(outfile=str(raw))
    proc, outputs = invoke(tmp_path, json.loads(raw.read_text()))
    assert proc.returncode == 0, proc.stderr
    totals = outputs["effective"]["totals"]
    assert totals["num_statements"] == 4
    assert totals["covered_lines"] == covered and totals["missing_lines"] == 4 - covered
    assert totals["num_branches"] == 2 and totals["covered_branches"] == branches
    assert totals["excluded_lines"] == 2
    assert totals["percent_covered"] == covered / 4 * 100


def test_invalid_rerun_replaces_previous_effective(tmp_path, sample):
    assert invoke(tmp_path, sample)[0].returncode == 0
    proc, outputs = invoke(tmp_path, "{")
    assert proc.returncode != 0
    assert outputs["effective"]["totals"] is None
    assert outputs["metadata"]["upload_allowed"] is False


def test_output_alias_does_not_overwrite_input(tmp_path):
    original = tmp_path / "raw.json"
    original.write_text("original", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--platform",
            "nvidia",
            "--source-sha",
            SHA,
            "--input",
            str(original),
            "--full-output",
            str(original),
            "--effective-output",
            str(tmp_path / "effective.json"),
            "--metadata-output",
            str(tmp_path / "metadata.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "must be distinct" in proc.stderr
    assert original.read_text() == "original"


@pytest.mark.parametrize(
    "key,value",
    [
        ("package_root", "elsewhere"),
        ("package_root", None),
        ("vendor_root", "outside/vendor"),
        ("vendor_root", "../vendor"),
        ("platforms", []),
        ("platforms", {"nvidia": {"mode": "typo", "backend": "cuda"}}),
    ],
)
def test_invalid_config_has_diagnostic_evidence(tmp_path, sample, key, value):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config[key] = value
    path = tmp_path / "scope.yml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    proc, outputs = invoke(tmp_path, sample, extra=("--config", str(path)))
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "invalid_input"
    assert outputs["metadata"]["upload_allowed"] is False


def test_malformed_yaml_has_diagnostic_evidence(tmp_path, sample):
    path = tmp_path / "scope.yml"
    path.write_text("platforms: [", encoding="utf-8")
    proc, outputs = invoke(tmp_path, sample, extra=("--config", str(path)))
    assert proc.returncode != 0
    assert outputs["metadata"]["error"] == "Invalid coverage scope YAML"


def test_duplicate_normalized_file_rejected(tmp_path):
    proc, outputs = invoke(
        tmp_path,
        report(
            {
                "vllm_fl/a.py": file_data([1], []),
                "C:\\repo\\vllm_fl\\a.py": file_data([1], []),
            }
        ),
    )
    assert proc.returncode != 0
    assert "Duplicate coverage file" in outputs["metadata"]["error"]


def test_package_root_is_used_not_hardcoded(tmp_path):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["package_root"] = "another_package"
    config["vendor_root"] = "another_package/vendor"
    path = tmp_path / "scope.yml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    proc, outputs = invoke(
        tmp_path,
        report(
            {
                "another_package/shared.py": file_data([1], [2]),
                "another_package/vendor/ascend/a.py": file_data([1], []),
            }
        ),
        extra=("--config", str(path)),
    )
    assert proc.returncode == 0
    assert outputs["effective"]["totals"]["num_statements"] == 2
    assert outputs["effective"]["totals"]["percent_covered"] == 50


def test_missing_input_replaces_stale_outputs_with_markers(tmp_path):
    paths = {
        name: tmp_path / f"{name}.json" for name in ("full", "effective", "metadata")
    }
    for path in paths.values():
        path.write_text('{"stale": true}', encoding="utf-8")
    args = [
        sys.executable,
        "-B",
        str(SCRIPT),
        "--platform",
        "nvidia",
        "--source-sha",
        SHA,
        "--input",
        str(tmp_path / "absent.json"),
    ]
    for name, path in paths.items():
        args.extend([f"--{name}-output", str(path)])
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode != 0
    for path in paths.values():
        payload = json.loads(path.read_text())
        assert payload["status"] == "missing_input"
        assert "stale" not in payload


@pytest.mark.parametrize(
    "summary",
    [
        {"num_branches": 2},
        {"num_branches": 2, "covered_branches": 3, "missing_branches": 0},
        {"num_branches": 2, "covered_branches": True, "missing_branches": 1},
        {
            "num_branches": 2,
            "covered_branches": 1,
            "missing_branches": 1,
            "num_partial_branches": 2,
        },
    ],
)
def test_invalid_optional_counts_rejected(tmp_path, summary):
    payload = report({"vllm_fl/a.py": file_data([1], [2])})
    payload["files"]["vllm_fl/a.py"]["summary"].update(summary)
    proc, outputs = invoke(tmp_path, payload)
    assert proc.returncode != 0
    assert outputs["metadata"]["status"] == "invalid_input"
