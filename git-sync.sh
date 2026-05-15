#!/usr/bin/env bash
set -euo pipefail

# WSL.sh version: sync branch with origin via rebase pull
BRANCH="${1:-main}"

echo "[1] fetch all"
git fetch --all --prune

echo "[2] switch branch: ${BRANCH}"
git checkout "${BRANCH}"

echo "[3] rebase pull from origin/${BRANCH}"
git pull --rebase origin "${BRANCH}"

echo "[4] status"
git status -sb
git log --oneline -n 5