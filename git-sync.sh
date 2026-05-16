#!/usr/bin/env bash
set -euo pipefail

# WSL.sh version: sync branch with origin via rebase pull
BRANCH="${1:-main}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree has uncommitted changes. Commit or stash them before sync."
  exit 1
fi

echo "[1] fetch all"
git fetch --all --prune

echo "[2] switch branch: ${BRANCH}"
if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git checkout "${BRANCH}"
elif git show-ref --verify --quiet "refs/remotes/origin/${BRANCH}"; then
  git checkout -b "${BRANCH}" --track "origin/${BRANCH}"
else
  echo "Branch origin/${BRANCH} does not exist."
  exit 1
fi

echo "[3] rebase pull from origin/${BRANCH}"
git pull --rebase origin "${BRANCH}"

echo "[4] status"
git status -sb
git log --oneline -n 5
