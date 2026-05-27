#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cmake -S "${REPO_DIR}" -B "${REPO_DIR}/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "${REPO_DIR}/build" --parallel "$(nproc)"

