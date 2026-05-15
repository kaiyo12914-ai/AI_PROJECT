param(
    [string]$Message = "chore: update"
)

$ErrorActionPreference = "Stop"

# Windows.ps1 version: commit and push current branch
$Branch = (git branch --show-current).Trim()

git add -A
$hasStaged = git diff --cached --name-only
if ([string]::IsNullOrWhiteSpace($hasStaged)) {
    Write-Host "No staged changes to commit."
} else {
    git commit -m $Message
}

git push -u origin $Branch
git status -sb