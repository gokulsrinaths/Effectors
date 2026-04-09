#!/usr/bin/env bash
# Bootstrap the hosted backend on Ubuntu.
# This script installs OS packages, creates the Python environment, and installs
# backend dependencies. It does not configure nginx or TLS automatically.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/effectors/Effectors}"
BACKEND_DIR="${REPO_ROOT}/backend"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "repo_root=${REPO_ROOT}"
echo "backend_dir=${BACKEND_DIR}"

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "Backend directory not found: ${BACKEND_DIR}"
  exit 1
fi

sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  nginx \
  curl

cd "${BACKEND_DIR}"

if [[ ! -d ".venv" ]]; then
  "${PYTHON_BIN}" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-hosted.txt

mkdir -p hosted_api/data/uploads hosted_api/data/results hosted_api/data/logs

echo
echo "Backend install complete."
echo "Next steps:"
echo "1. Copy deploy/linux/env.backend.example to your real env file"
echo "   cp deploy/linux/env.backend.example deploy/linux/env.backend"
echo "2. Install TM-align and BLAST+ if you need the full biology pipeline"
echo "3. Install and enable systemd and nginx configs from deploy/linux/"
