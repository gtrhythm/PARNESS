#!/usr/bin/env bash
# Wrapper that runs any python command in the dedicated PEK conda env.
#
# Why this exists:
#   - PEK needs paddlepaddle-gpu 2.6.2 (GPU-compiled) which conflicts with
#     other ATM components living in /usr/bin/python3 or .venv.
#   - conda-forge's libstdc++ must load before the system one, hence the
#     explicit LD_LIBRARY_PATH override (Ubuntu 22.04 ships gcc 12 but
#     conda's _sqlite3 needs CXXABI_1.3.15 from gcc 14).
#
# Usage:
#   ./scripts/run_pek_env.sh python -m src.pdf_parser.daemon.server ...
#   ./scripts/run_pek_env.sh python scripts/bench_pek.py --pdf-list-file ...
#   CUDA_VISIBLE_DEVICES=1 ./scripts/run_pek_env.sh python scripts/run_pipeline.py ...

set -euo pipefail

PEK_ENV_PREFIX="${PEK_ENV_PREFIX:-/opt/conda/envs/pek}"

if [[ ! -x "${PEK_ENV_PREFIX}/bin/python" ]]; then
    echo "PEK conda env not found at ${PEK_ENV_PREFIX}." >&2
    echo "Create with: conda create -n pek python=3.10 && pip install -r src/PDF-Extract-Kit/requirements.txt" >&2
    exit 1
fi

export LD_LIBRARY_PATH="${PEK_ENV_PREFIX}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${PEK_ENV_PREFIX}/bin:${PATH}"

# The first arg might be "python" or absolute path; rewrite to the env's python
if [[ "${1:-}" == "python" || "${1:-}" == "python3" ]]; then
    shift
    exec "${PEK_ENV_PREFIX}/bin/python" "$@"
else
    exec "$@"
fi
