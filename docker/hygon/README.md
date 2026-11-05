# Hygon vLLM 0.28 CI image on runtime 2.3.0

Build and final-container validation are in progress. Do not treat a local tag
or a successful intermediate container test as a published, validated image.

This recipe starts its runtime from
`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.3.0`, pinned to
`sha256:03e598b348e58e7233628394bbefa0ccef26969a091c7e6f2f02835161757f8b`.
The base is Ubuntu 24.04, Python 3.10.20, and DTK 26.04. Its Torch 2.9 stack is
replaced with the Torch 2.10 stack from the historical validated Hygon image.

The artifact stage is pinned to
`harbor.baai.ac.cn/plugin/vllm-plugin-fl@sha256:e5a84bc28e4bfcae413e1e9288a605a49aea352ecc8b35f4b58b3ebba5e6fc9d`.
It reconstructs ordinary wheels from the installed Torch, FlagGems, Triton,
torchvision and flash-attn packages. These are reconstructed artifacts, not
byte-identical copies of the original vendor wheels. Original RECORD hashes
are verified; Triton shared files are checked against FlagTree's RECORD. The
one existing backend-discovery patch is explicitly bound to its SHA256 in the
repack script. The original FlagTree wheel is separately verified against its
published hash. Runtime code is never loaded from an editable checkout.

| Component | Selected version |
| --- | --- |
| Torch | 2.10.0+das.opt1.dtk2604.20260325.g6b060a |
| vLLM | 0.28.0+empty |
| FlagGems | 0.1.0, from the pinned validation image |
| FlagTree | 0.6.0+hcu3.6 |
| Triton | 3.6.0+gitc73250c4.staging |
| FL source | 72eaf18e61d5015b70988cb03a7ba3eeee0dc8b9 |
| FlagGems-vllm source | f775b37f3066e2935742d26c7592a5dd55499159 |
| Communication | Vendor RCCL; FlagCX removed |

The base's FlagCX extension is compiled against Torch 2.9 and fails to load
with Torch 2.10. It is removed from this image. Keep `FLAGCX_PATH` unset.
`runtime-env.sh` replaces the base's dynamic compiler selection so login
shells consistently use the fixed installed compiler in `/flagos`.

vLLM's original OpenCV requirement selects NumPy 2 wheels. This recipe keeps
the base's NumPy 1.26.4, uses OpenCV 4.11.0.86, and patches only the empty
wheel's OpenCV dependency declaration and RECORD. Runtime source is unchanged.
This explicit local metadata change is recorded by `patch-vllm-wheel.py`.
The supplemented test container passes `pip check` after this adjustment.

The Dockerfile embeds all changed public package pins, including the extra
CI dependencies discovered by the full test run. Build artifacts and source
checkouts are retained; no `rm` cleanup is required. Aiter is not repackaged:
the historical installation contains missing build-cache entries, so that
artifact failed validation and is excluded.

Build from the repository root on an AMD64 Linux host with access to the two
pinned Harbor images, GitHub and the selected Python index:

```bash
DOCKER_BUILDKIT=0 docker build --network host \
  -f docker/hygon/Dockerfile.v0.28.0 \
  -t vllm-fl-hygon:runtime2.3.0-ci-20261105 .
```

The recipe supports legacy Docker; it does not require buildx. Build does not
need DCU device access. It records the installed package lock and source SHAs
under `/opt/release`. The installed source tree is retained under `/opt/src`.

Runtime tests need two idle DCUs, the Hygon driver mount, and local model files.
Resolve render-node mappings on your host instead of copying physical device
indices. The validation host used renderD130/renderD131, exposed as logical
0/1 inside the isolated container. Models were read-only mounted from
`/data/models/Qwen`, with Qwen3.6-27B and Qwen3.6-35B-A3B TP2 cases selected by
`tests/platforms/hygon.yaml`. Use `VLLM_USE_V2_MODEL_RUNNER=0`.

The original full run passed functional, offline inference, text/image
serving and benchmark smoke but had one timing-sensitive cleanup unit test
failure. The unchanged complete unit suite then passed on retry: 1866 passed,
103 skipped in parallel; 2 passed and 20 skipped in the serial selection.
After the OpenCV adjustment, functional tests passed again (23 passed,
77 skipped); the model/benchmark matrix and final image build are in progress.
Failure logs are retained; no assertions or test selection were weakened.

Current operational note: the build reached the public dependency installation
stage but waited during network queries. The bastion session subsequently
became stuck in its command-confirmation prompt while attempting to stop only
that build container. Build completion and final model retest results must be
read after a fresh SSH login. No image from this rebuild has been published.
