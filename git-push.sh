#!/usr/bin/env bash
set -euo pipefail

# WSL.sh version: commit and push current branch
MSG="${1:-chore: update}"
BRANCH="$(git branch --show-current)"

git add -A
if git diff --cached --quiet; then
  echo "No staged changes to commit."
else
  git commit -m "${MSG}"
fi

git push -u origin "${BRANCH}"
git status -sb