#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CV_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PRESET="${1:-segmentation}"

case "${PRESET}" in
  segmentation)
    VENV_PATH="${CV_ROOT}/.venv-segmentation"
    REQUIREMENTS_PATHS=(
      "${CV_ROOT}/requirements/segmentation-lab.txt"
    )
    ;;
  segmentation-notebook)
    VENV_PATH="${CV_ROOT}/.venv-segmentation-notebook"
    REQUIREMENTS_PATHS=(
      "${CV_ROOT}/requirements/segmentation-lab.txt"
      "${CV_ROOT}/requirements/notebook-tools.txt"
    )
    ;;
  training)
    VENV_PATH="${CV_ROOT}/.venv-training"
    REQUIREMENTS_PATHS=(
      "${CV_ROOT}/requirements/training-lab.txt"
    )
    ;;
  *)
    echo "Unsupported preset: ${PRESET}" >&2
    echo "Usage: bash scripts/bootstrap_cv_env.sh [segmentation|segmentation-notebook|training]" >&2
    exit 2
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

python3 -m venv "${VENV_PATH}"
source "${VENV_PATH}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
for requirements_path in "${REQUIREMENTS_PATHS[@]}"; do
  python -m pip install -r "${requirements_path}"
done

echo
echo "CV environment ready:"
echo "  preset: ${PRESET}"
echo "  venv:   ${VENV_PATH}"
echo
echo "Activate it with:"
echo "  source ${VENV_PATH}/bin/activate"
