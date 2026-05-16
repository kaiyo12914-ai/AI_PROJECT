#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:-main}"
REMOTE="${GIT_REMOTE:-origin}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git work tree"

ORIGIN_URL="$(git config --get "remote.${REMOTE}.url" || true)"
[[ -n "${ORIGIN_URL}" ]] || die "remote '${REMOTE}' is not configured"
[[ "${ORIGIN_URL}" != *"H:\\"* ]] || die "remote '${REMOTE}' uses a Windows local path; set it to the GitHub repository URL"
[[ "${ORIGIN_URL}" != /mnt/a_git/* ]] || die "remote '${REMOTE}' uses deprecated /mnt/a_git local hub; set it to the GitHub repository URL"

if [[ -n "$(git status --porcelain)" ]]; then
  git status -sb
  die "working tree has uncommitted changes; commit/stash them before syncing"
fi

echo "[1] fetch ${REMOTE}"
git fetch "${REMOTE}" --prune

if ! git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}"; then
  git branch -r
  die "remote branch ${REMOTE}/${BRANCH} does not exist"
fi

echo "[2] switch branch: ${BRANCH}"
if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git checkout "${BRANCH}"
else
  git checkout -b "${BRANCH}" "${REMOTE}/${BRANCH}"
fi

if [[ -n "$(git status --porcelain)" ]]; then
  git status -sb
  die "working tree has uncommitted changes on ${BRANCH}; commit/stash them before syncing"
fi

echo "[3] fast-forward from ${REMOTE}/${BRANCH}"
git merge --ff-only "${REMOTE}/${BRANCH}"
git branch --set-upstream-to="${REMOTE}/${BRANCH}" "${BRANCH}" >/dev/null

echo "[4] status"
git status -sb
git log --oneline --decorate -n 5
