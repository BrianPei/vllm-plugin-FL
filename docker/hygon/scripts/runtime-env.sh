#!/bin/bash
# Fixed runtime packages in /flagos; retain vendor SDK environment.
export PATH="/flagos/bin:$PATH"
unset PYTHONPATH PYTHONHOME FLAGCX_PATH VLLM_VENDOR
export GEMS_VENDOR=hygon USE_FLAGGEMS=1 VLLM_PLUGINS=fl
export VLLM_USE_V2_MODEL_RUNNER=0
export ROCM_PATH=/opt/dtk HIP_PATH=/opt/dtk/hip DTKROOT=/opt/dtk
export HYGON_FLAGGEMS_VERSION=0.1.0 HYGON_FLAGTREE_VERSION=0.6.0+hcu3.6
