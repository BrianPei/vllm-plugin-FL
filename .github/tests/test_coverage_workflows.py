"""Static regression checks for evidence retention and publication guards."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["_unit_test.yml", "_functional_test.yml"])
def workflow(request):
    # BaseLoader preserves the Actions key 'on' instead of YAML 1.1 boolean True.
    return yaml.load(
        (ROOT / ".github/workflows" / request.param).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def steps(workflow):
    return next(iter(workflow["jobs"].values()))["steps"]


def test_actual_checkout_sha_and_test_outcomes_are_passed(workflow):
    by_id = {step["id"]: step for step in steps(workflow) if "id" in step}
    assert "git rev-parse HEAD" in by_id["source"]["run"]
    command = by_id["coverage"]["run"]
    assert '--source-sha "${{ steps.source.outputs.sha }}"' in command
    assert '--unit-status "${{ steps.unit.outcome }}"' in command
    if "functional" in by_id:
        assert '--functional-status "${{ steps.functional.outcome }}"' in command
    else:
        assert "--functional-status skipped" in command
    assert "GITHUB_SHA" not in command


def test_failed_tests_still_produce_and_retain_evidence(workflow):
    compute = next(step for step in steps(workflow) if step.get("id") == "coverage")
    assert compute["if"] == "${{ !cancelled() && steps.source.outcome == 'success' }}"
    assert "continue-on-error" not in compute
    artifact = next(
        step
        for step in steps(workflow)
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert artifact["if"] == "always()"
    for suffix in ("-full.json", "-effective.json", "-scope.json"):
        filename = "coverage-${{ inputs.platform }}" + suffix
        assert filename in artifact["with"]["path"]
        assert filename in compute["run"]
    assert "--input coverage-${{ inputs.platform }}.json" in compute["run"]


def test_only_valid_effective_report_is_publishable(workflow):
    upload = next(
        step
        for step in steps(workflow)
        if "post-pytest-report@" in step.get("uses", "")
    )
    assert upload["uses"] == "flagos-ai/FlagOps/actions/post-pytest-report@v2"
    assert upload["with"]["file_type"] == "coverage"
    by_id = {step["id"]: step for step in steps(workflow) if "id" in step}
    scope = "unit,functional" if "functional" in by_id else "unit"
    assert by_id["coverage"]["run"].split("--scope ", 1)[1].split()[0] == scope
    assert upload["with"]["job_name"] == "coverage-${{ inputs.platform }}-" + scope
    assert (
        upload["with"]["report_path"]
        == "coverage-${{ inputs.platform }}-effective.json"
    )
    guard = upload["if"]
    for condition in (
        "success()",
        "steps.coverage.outcome == 'success'",
        "steps.unit.outcome == 'success'",
        "steps.flagcicd.outputs.configured == 'true'",
    ):
        assert condition in guard
    assert "||" not in guard  # no alternate path around the fail-closed conditions
    if any(step.get("id") == "functional" for step in steps(workflow)):
        assert "steps.functional.outcome == 'success'" in guard
    else:
        assert "inputs.upload_coverage" in guard
        assert (
            workflow["on"]["workflow_call"]["inputs"]["upload_coverage"]["type"]
            == "boolean"
        )
    assert (
        workflow["on"]["workflow_call"]["secrets"]["FLAGCICD_API_TOKEN"]["required"]
        == "false"
    )


def test_active_platform_chain_uses_combined_workflow_once():
    platform = yaml.load(
        (ROOT / ".github/workflows/_platform_test.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    calls = [job.get("uses") for job in platform["jobs"].values()]
    assert calls.count("./.github/workflows/_functional_test.yml") == 1
    assert "./.github/workflows/_unit_test.yml" not in calls
