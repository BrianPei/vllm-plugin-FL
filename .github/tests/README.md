# Coverage tooling regression tests and review

Synchronization baseline: `ci/test-coverage` at `f539a9c832db81e99ee5f1ce81f5d283c713e5ef`.
The original local contribution at `f026e89` is preserved in the merge history.

## Run without GPUs

From the repository root, use a Python environment containing pytest, PyYAML and
coverage.py. The dedicated `coverage-scope-tests.yml` workflow installs pinned
test tools and runs this suite on a hosted CPU runner. It does not install the
project or publish coverage metrics.

```sh
python -m pytest .github/tests -q -o addopts= --junitxml=coverage-scope-tests.xml
```

These tests live outside `tests/` so they do not load the GPU-dependent project
conftest files. The coverage fixtures include actual coverage.py branch reports,
excluded statements, and persisted data loaded and appended across two runs.
Synthetic fixtures check the exact numerator, denominator, exclusions, weighted
totals, malformed input, package boundaries, path formats and evidence outputs.
Platform expectations follow the current trimmed configuration. Removed aliases
are not restored; Hygon keeps the upstream shared-only rule.

## Failure and evidence contract

| Status | Effective output | Full output | Exit / publication |
| --- | --- | --- | --- |
| `ok` | Existing platform rules; statement-weighted percentage | Exact original bytes | Success; workflow additionally requires successful test steps and credentials |
| `empty_scope` | Zero statements; percentage null, display `N/A` | Exact original bytes | Failure; no upload |
| `invalid_input` | Diagnostic object, null totals | Exact original bytes, even if malformed JSON | Failure; no upload |
| `missing_input` | Diagnostic object, null totals | Explicit missing-input marker | Failure; no upload |

Full, Effective, metadata and input paths must be distinct. Error outputs replace
previous Effective/metadata files so a failed retry cannot leave a valid-looking
old metric. Metadata records requested scope separately from actual unit and
functional step outcomes. `upload_allowed` describes metric validation; workflow
combined-workflow publication additionally checks test success and credentials.
The standalone unit workflow retains and publishes its raw full-package report;
it does not call the scope processor or generate Full/Effective/metadata files.
Its publication checks test success, credentials, report existence and the
`upload_coverage` switch. Its raw report does not receive scope-processor validation.
Audit artifacts are retained independently of that switch.
Configuration hashes allow the selected ownership configuration to be traced.

The effective top-level percentage continues to mean covered Python statements
divided by applicable Python statements. Branch-enabled input is rejected,
matching the upstream statement-only policy. The original bytes remain in Full
and diagnostic metadata blocks publication. Valid reports also expose the native
`percent_statements_covered` keys. With the trimmed configuration, the package
root defaults to `vllm_fl`; removed configuration entries are not reintroduced.
Full reports and per-file coverage.py details remain unchanged. Native coverage is
outside this tool's scope.

## FlagCICD contract investigation

Reviewed on 2026-11-09 (v2 at `466de7d164bf6ca3989c0abaeba1c3a62c68a047`):
[FlagOps post-pytest-report v2 action](https://github.com/flagos-ai/FlagOps/blob/466de7d164bf6ca3989c0abaeba1c3a62c68a047/actions/post-pytest-report/action.yml).
Its `Resolve inputs and validate` step checks credentials and file existence.
Its `Upload report` step sends the file as multipart form data. It does not
validate coverage JSON or specify whether null/N/A percentages are accepted by
the server. No server request or test upload was performed. Server-side N/A
acceptance therefore remains unconfirmed; invalid and empty metrics fail closed.
Both workflows explicitly set `file_type: coverage` (the Action defaults to
`pytest`) and `job_name: coverage-<platform>-<scope>`. Scope is the existing
`unit` or `unit,functional` value; no device segment is added because these
workflows have no device input. `file_format` retains its `json` default.

## Ownership decisions deliberately deferred

- Hygon: `vllm_fl/utils.py` maps it to CUDA-like device names;
  `dispatch/builtin_ops.py` can resolve and invoke the CUDA registration module.
  `CudaBackend.is_available()` rejecting a device does not prove that all code
  in the directory is outside that platform's verification responsibilities.
  Keep the current shared-only rule until the owner specifies applicability.
- AMD: independently maps to CUDA-like device names and resolves the CUDA
  directory, but has no dedicated entry in current CI platform/test YAMLs.
  `platform.py` also derives the runtime device name; Hygon's reasoning must not
  be copied without checking that path. No mapping was changed.
- NVIDIA model paths: `models/qwen3_8_flash_next/gpu/nvidia_fast_paths.py`
  contains runtime checks and fallbacks outside the vendor directory. A filename
  or skipped path is insufficient exclusion evidence. These files remain counted.
- A future ownership manifest needs evidence-backed shared/platform-owned and
  not-applicable rules. Applicable uncovered statements are coverage gaps and
  must remain in the denominator. This patch does not implement new ownership
  rules, remove disabled platforms/aliases, or alter test selection.

## Local verification limits

Synchronization validation on 2026-11-10: 68 CPU-only coverage/workflow regression
tests passed on Windows / Python 3.14. This includes real statement reports,
branch-report rejection, invalid and empty input, evidence retention, the trimmed
platform mappings and the standalone unit workflow's raw-report contract.
The hosted workflow targets Python 3.12 and has not been triggered here.
Full project tests, GPU execution and actual FlagCICD ingestion remain unverified.

Actionlint 1.7.7 reports the inherited dynamic `container.volumes` scalar in both
reusable workflows. The same diagnostics are checked against upstream `f539a9c`.
ShellCheck and Pyflakes integrations are disabled for this comparison.
Local JUnit results and generated fixtures are retained under `.review-evidence/`
and are not PR source files.
