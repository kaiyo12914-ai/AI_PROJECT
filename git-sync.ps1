param(
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

# Windows.ps1 version: sync branch with origin via rebase pull
Write-Host "[1] fetch all"
git fetch --all --prune

Write-Host "[2] switch branch: $Branch"
git checkout $Branch

Write-Host "[3] rebase pull from origin/$Branch"
git pull --rebase origin $Branch

Write-Host "[4] status"
git status -sb
git log --oneline -n 5