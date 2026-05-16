param(
    [string]$Branch = "main",
    [string]$Remote = "origin"
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Error $Message
    exit 1
}

git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Fail "not inside a git work tree" }

$originUrl = (git config --get "remote.$Remote.url")
if ([string]::IsNullOrWhiteSpace($originUrl)) { Fail "remote '$Remote' is not configured" }

if ($originUrl -like "H:\*") { Fail "remote '$Remote' uses a Windows local path; set it to the GitHub repository URL" }
if ($originUrl -like "/mnt/a_git/*") { Fail "remote '$Remote' uses deprecated /mnt/a_git local hub; set it to the GitHub repository URL" }

$dirty = (git status --porcelain)
if (-not [string]::IsNullOrWhiteSpace($dirty)) {
    git status -sb
    Fail "working tree has uncommitted changes; commit/stash them before syncing"
}

Write-Host "[1] fetch $Remote"
git fetch $Remote --prune

git show-ref --verify --quiet "refs/remotes/$Remote/$Branch"
if ($LASTEXITCODE -ne 0) {
    git branch -r
    Fail "remote branch $Remote/$Branch does not exist"
}

Write-Host "[2] switch branch: $Branch"
git show-ref --verify --quiet "refs/heads/$Branch"
if ($LASTEXITCODE -eq 0) {
    git checkout $Branch
} else {
    git checkout -b $Branch "$Remote/$Branch"
}

Write-Host "[3] fast-forward from $Remote/$Branch"
git merge --ff-only "$Remote/$Branch"
git branch --set-upstream-to="$Remote/$Branch" $Branch *> $null

Write-Host "[4] status"
git status -sb
git log --oneline --decorate -n 5
