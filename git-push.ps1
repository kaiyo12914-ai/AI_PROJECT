param(
    [string]$Message = "chore: update",
    [string]$Remote = "upstream"
)

$ErrorActionPreference = "Stop"

function Fail($MessageText) {
    Write-Error $MessageText
    exit 1
}

git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Fail "not inside a git work tree" }

$Branch = (git branch --show-current).Trim()
if ([string]::IsNullOrWhiteSpace($Branch)) { Fail "detached HEAD; checkout a branch before pushing" }

$originUrl = (git config --get "remote.$Remote.url")
if ([string]::IsNullOrWhiteSpace($originUrl)) { Fail "remote '$Remote' is not configured" }

if ($originUrl -like "H:\*") { Fail "remote '$Remote' uses a Windows local path; set it to the GitHub repository URL" }
if ($originUrl -like "/mnt/a_git/*") { Fail "remote '$Remote' uses deprecated /mnt/a_git local hub; set it to the GitHub repository URL" }

Write-Host "[1] stage changes"
git add -A -- . `
    ':(exclude).env' `
    ':(exclude).env.*' `
    ':(exclude)venv/**' `
    ':(exclude).venv/**' `
    ':(exclude).venv-win/**' `
    ':(exclude)venv_windows/**' `
    ':(exclude)venv_old/**'

$hasStaged = git diff --cached --name-only
if ([string]::IsNullOrWhiteSpace($hasStaged)) {
    Write-Host "No staged changes to commit."
} else {
    Write-Host "[2] commit"
    git commit -m $Message
}

Write-Host "[3] fetch $Remote"
git fetch $Remote --prune

git show-ref --verify --quiet "refs/remotes/$Remote/$Branch"
if ($LASTEXITCODE -eq 0) {
    $localRef = (git rev-parse $Branch).Trim()
    $remoteRef = (git rev-parse "$Remote/$Branch").Trim()
    $baseRef = (git merge-base $Branch "$Remote/$Branch").Trim()
    if (($localRef -ne $remoteRef) -and ($baseRef -ne $remoteRef)) {
        Fail "$Remote/$Branch has commits not in local $Branch; run .\git-sync.ps1 -Branch $Branch first"
    }
}

Write-Host "[4] push $Branch"
git push -u $Remote $Branch
git status -sb
