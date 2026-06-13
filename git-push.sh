#!/usr/bin/env bash
set -euo pipefail

MSG="${1:-chore: update}"
REMOTE="${GIT_REMOTE:-upstream}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git work tree"

BRANCH="$(git branch --show-current)"
[[ -n "${BRANCH}" ]] || die "detached HEAD; checkout a branch before pushing"

ORIGIN_URL="$(git config --get "remote.${REMOTE}.url" || true)"
[[ -n "${ORIGIN_URL}" ]] || die "remote '${REMOTE}' is not configured"
[[ "${ORIGIN_URL}" != *"H:\\"* ]] || die "remote '${REMOTE}' uses a Windows local path; set it to the GitHub repository URL"
[[ "${ORIGIN_URL}" != /mnt/a_git/* ]] || die "remote '${REMOTE}' uses deprecated /mnt/a_git local hub; set it to the GitHub repository URL"

echo "[1] fetch ${REMOTE}"
git fetch "${REMOTE}" --prune

if git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}"; then
  LOCAL="$(git rev-parse "${BRANCH}")"
  REMOTE_REF="$(git rev-parse "${REMOTE}/${BRANCH}")"
  BASE="$(git merge-base "${BRANCH}" "${REMOTE}/${BRANCH}")"
  if [[ "${LOCAL}" != "${REMOTE_REF}" && "${BASE}" != "${REMOTE_REF}" ]]; then
    die "${REMOTE}/${BRANCH} has commits not in local ${BRANCH}; run bash git-sync.sh ${BRANCH} first"
  fi
fi

echo "[2] stage changes"
git add -A -- . \
  ':(exclude).env' \
  ':(exclude).env.*' \
  ':(exclude)venv/**' \
  ':(exclude).venv/**' \
  ':(exclude).venv-win/**' \
  ':(exclude)venv_windows/**' \
  ':(exclude)venv_old/**'

if git diff --cached --quiet; then
  echo "No staged changes to commit."
else
  echo "[3] commit"
  git commit -m "${MSG}"
fi

echo "[4] push ${BRANCH}"
git push -u "${REMOTE}" "${BRANCH}"
git status -sb
