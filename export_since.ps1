# export_since.ps1 (Windows PowerShell 5.1 compatible; args-only; NO param block)
# - Generates: filestru_since_YYYYMMDD.txt, exportfile_since_YYYYMMDD_export_YYYYMMDD.zip, install.ps1
# - Final bundle: exportfile_MMdd_HHmm.ZIP (contains the 3 files above)
# - Filters: LastWriteTime >= SinceDate 00:00:00
# Usage:
#   powershell -ExecutionPolicy Bypass -File H:\AI\DJANGO\export_since.ps1 -BasePath H:\AI\DJANGO -Since 20260114
#   powershell -ExecutionPolicy Bypass -File H:\AI\DJANGO\export_since.ps1 -BasePath H:\AI\DJANGO -Since 2026-01-14
#   powershell -ExecutionPolicy Bypass -File H:\AI\DJANGO\export_since.ps1 20260114

try { chcp 65001 | Out-Null } catch { }

# ✅ IMPORTANT: capture script args (because $args inside functions is function-local)
$SCRIPT_ARGS = @($args)
Write-Host ("ARGS: " + ($SCRIPT_ARGS -join " | "))

# -------------------------
# helpers
# -------------------------
function ArgKeyEquals([string]$a, [string]$b) {
  if ([string]::IsNullOrWhiteSpace($a) -or [string]::IsNullOrWhiteSpace($b)) { return $false }
  return [string]::Equals($a, $b, [System.StringComparison]::InvariantCultureIgnoreCase)
}

function Get-ArgValue([string]$name) {
  $alt = "/" + $name.TrimStart("-")
  for ($i=0; $i -lt $SCRIPT_ARGS.Count; $i++) {
    $k = [string]$SCRIPT_ARGS[$i]
    if ([string]::IsNullOrWhiteSpace($k)) { continue }

    if (ArgKeyEquals $k $name -or ArgKeyEquals $k $alt) {
      if (($i+1) -lt $SCRIPT_ARGS.Count) { return [string]$SCRIPT_ARGS[$i+1] }
    }
  }
  return $null
}

function Get-RelPath([string]$Base, [string]$Full) {
  if ($null -eq $Base -or $null -eq $Full) { return '' }
  if ($Full.Length -le $Base.Length) { return '' }
  $rel = $Full.Substring($Base.Length)
  return $rel.TrimStart('\','/')
}

# .gitignore folder filter helper (uses git status --ignored)
$script:GitIgnoreEnabled = $false
$script:IgnoredDirs = @()
function Init-GitIgnoreFilter([string]$Base) {
  $script:GitIgnoreEnabled = $false
  $script:IgnoredDirs = @()
  if ([string]::IsNullOrWhiteSpace($Base)) { return }
  if (-not (Test-Path (Join-Path $Base ".gitignore"))) { return }

  $gitCmd = Get-Command git -ErrorAction SilentlyContinue
  if ($null -eq $gitCmd) { return }

  # quick probe: must be a git work tree
  $probe = & git -C $Base rev-parse --is-inside-work-tree 2>$null
  if ($LASTEXITCODE -eq 0 -and [string]$probe -match "true") {
    $script:GitIgnoreEnabled = $true
  }

  if (-not $script:GitIgnoreEnabled) { return }

  # Collect currently ignored directories only (not files)
  $status = & git -C $Base status --ignored --porcelain=1 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $status) { return }

  $dirs = New-Object System.Collections.Generic.List[string]
  foreach ($line in $status) {
    $s = [string]$line
    if (-not $s.StartsWith("!! ")) { continue }
    $p = $s.Substring(3).Trim()
    if ([string]::IsNullOrWhiteSpace($p)) { continue }
    if (-not $p.EndsWith("/")) { continue } # folders only

    $relDir = $p.TrimEnd('/').Replace('/','\')
    if ([string]::IsNullOrWhiteSpace($relDir)) { continue }
    $fullDir = Join-Path $Base $relDir
    try {
      $resolved = (Resolve-Path -LiteralPath $fullDir -ErrorAction Stop).Path
      if (-not $dirs.Contains($resolved)) { $dirs.Add($resolved) }
    } catch {
      # ignore non-existing path
    }
  }
  $script:IgnoredDirs = @($dirs)
}

function Test-IsInGitIgnoredDir([string]$Base, [string]$Full) {
  if (-not $script:GitIgnoreEnabled) { return $false }
  if (-not $script:IgnoredDirs -or $script:IgnoredDirs.Count -eq 0) { return $false }
  $fullNorm = [string]$Full
  foreach ($d in $script:IgnoredDirs) {
    if ([string]::IsNullOrWhiteSpace($d)) { continue }
    if ($fullNorm.StartsWith($d + "\")) { return $true }
  }
  return $false
}

function Parse-SinceDate([string]$s) {
  if ([string]::IsNullOrWhiteSpace($s)) { return $null }

  $s2 = $s.Trim()
  $dt = New-Object DateTime

  # ✅ PowerShell 5.1 / .NET Framework: must use CultureInfo + string[]
  $culture = [System.Globalization.CultureInfo]::InvariantCulture
  $formats = [string[]]@("yyyyMMdd","yyyy-MM-dd","yyyy/MM/dd")

  $ok = [datetime]::TryParseExact(
    $s2,
    $formats,
    $culture,
    [System.Globalization.DateTimeStyles]::None,
    [ref]$dt
  )

  if ($ok) { return $dt.Date }

  # fallback: general parse (still with culture)
  $dt2 = New-Object DateTime
  $ok2 = [datetime]::TryParse(
    $s2,
    $culture,
    [System.Globalization.DateTimeStyles]::None,
    [ref]$dt2
  )

  if ($ok2) { return $dt2.Date }
  return $null
}

function New-ZipFromFileList([string]$ZipPath, $Files, [string]$BasePath) {
  if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
  if ($null -eq $Files -or $Files.Count -eq 0) {
    throw "No files to zip."
  }

  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem

  $fs = $null
  $zip = $null
  try {
    $fs = [System.IO.File]::Open($ZipPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create, $false)

    foreach ($f in $Files) {
      $rel = Get-RelPath $BasePath $f.FullName
      if ([string]::IsNullOrWhiteSpace($rel)) { continue }
      $entryName = $rel.Replace('\','/')

      $entry = $zip.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
      $inStream = $null
      $outStream = $null
      try {
        $inStream = [System.IO.File]::OpenRead($f.FullName)
        $outStream = $entry.Open()
        $inStream.CopyTo($outStream)
      } finally {
        if ($outStream) { $outStream.Dispose() }
        if ($inStream) { $inStream.Dispose() }
      }
    }
  } finally {
    if ($zip) { $zip.Dispose() }
    if ($fs) { $fs.Dispose() }
  }
}

# -------------------------
# BasePath / OutDir
# -------------------------
$BasePath = Get-ArgValue "-BasePath"
if ([string]::IsNullOrWhiteSpace($BasePath)) { $BasePath = "H:\AI\DJANGO" }

$OutDir = Join-Path $PSScriptRoot "export_out"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# init gitignore matcher (best-effort)
Init-GitIgnoreFilter $BasePath

# -------------------------
# Since (MUST)
# -------------------------
$SinceText = Get-ArgValue "-Since"
if ([string]::IsNullOrWhiteSpace($SinceText)) {
  # positional fallback: export_since.ps1 20260114
  if ($SCRIPT_ARGS.Count -ge 1 -and $SCRIPT_ARGS[0] -notlike "-*" -and $SCRIPT_ARGS[0] -notlike "/*") {
    $SinceText = [string]$SCRIPT_ARGS[0]
  }
}

Write-Host ("SinceText: " + $SinceText)

$SinceDate = Parse-SinceDate $SinceText
if ($null -eq $SinceDate) {
  Write-Host "ERROR: -Since date parse failed."
  Write-Host ("  Raw SinceText: " + ($SinceText))
  Write-Host "  Accepted: yyyyMMdd or yyyy-MM-dd or yyyy/MM/dd"
  exit 1
}

# -------------------------
# file patterns
# -------------------------
$Exts = @('*.js','*.py','*.html','*.css','*.json','*.txt','*.md')
$ExtSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::InvariantCultureIgnoreCase)
foreach ($e in $Exts) {
  $v = [string]$e
  if ([string]::IsNullOrWhiteSpace($v)) { continue }
  $ext = $v.Trim().TrimStart('*')
  if ([string]::IsNullOrWhiteSpace($ext)) { continue }
  if (-not $ext.StartsWith('.')) { $ext = "." + $ext }
  [void]$ExtSet.Add($ext)
}

# -------------------------
# output names
# -------------------------
$TodayTag = (Get-Date).ToString('yyyyMMdd')      # ZIP uses export run date (no HHmmss)
$SinceTag = $SinceDate.ToString('yyyyMMdd')      # LIST uses since date

# ✅ NEW zip naming (avoid confusion)
$ZipName  = "exportfile_since_${SinceTag}_export_${TodayTag}.zip"
$ZipPath  = Join-Path $OutDir $ZipName

$ListName = "filestru_since_$SinceTag.txt"
$ListPath = Join-Path $OutDir $ListName

$InstallPath = Join-Path $OutDir "install.ps1"

# -------------------------
# collect files
# -------------------------
$files = Get-ChildItem -Path $BasePath -Recurse -File |
  Where-Object {
    $ExtSet.Contains($_.Extension) -and
    $_.LastWriteTime -ge $SinceDate -and
    ($_.FullName -notlike (Join-Path $OutDir '*')) -and
    (-not (Test-IsInGitIgnoredDir $BasePath $_.FullName))
  } |
  Sort-Object LastWriteTime

# -------------------------
# write list
# -------------------------
$header = @()
$header += "BasePath: $BasePath"
$header += "ExportDate: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$header += "SinceDate: $($SinceDate.ToString('yyyy-MM-dd 00:00:00'))"
$header += "Criteria: LastWriteTime >= $($SinceDate.ToString('yyyy-MM-dd 00:00:00'))"
$header += "Extensions: $($Exts -join ', ')"
$header += "GitIgnoreFolderFilter: $(if ($script:GitIgnoreEnabled) { 'enabled (folders only)' } else { 'disabled (git/.gitignore not available)' })"
$header += "IgnoredFoldersCount: $($script:IgnoredDirs.Count)"
$header += "Count: $($files.Count)"
$header += "------------------------------------------------------------"
$header += "LastWriteTime`tSize(bytes)`tRelativePath"
$header += "------------------------------------------------------------"

if (-not $files -or $files.Count -eq 0) {
  ($header + @('(no matched files)')) | Out-File -FilePath $ListPath -Encoding utf8
  Write-Host "No matched files. List written:"
  Write-Host $ListPath
  exit 0
}

$lines = foreach ($f in $files) {
  $rel = Get-RelPath $BasePath $f.FullName
  "{0}`t{1}`t{2}" -f ($f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')), $f.Length, $rel
}
($header + $lines) | Out-File -FilePath $ListPath -Encoding utf8

# -------------------------
# zip
# -------------------------
New-ZipFromFileList -ZipPath $ZipPath -Files $files -BasePath $BasePath

# -------------------------
# install.ps1 (args-only; NO param)  ✅ FIXED: supports new zip naming + -SinceTag
# -------------------------
$installContent = @'
# install.ps1 (NO param block; args-only; ultra compatible; PS 5.1)
# Supports:
#   -TargetDir <path>   (required unless positional)
#   -ZipPath <zip>      (optional: apply a single specified zip)
#   -SinceTag <YYYYMMDD> (optional: auto pick latest zip for that since)
# Notes:
#   Preferred zip name: exportfile_since_YYYYMMDD_export_YYYYMMDD.zip
#   Fallback old name:  exportfile_YYYYMMDD.zip
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 D:\AI\DJANGO
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -TargetDir D:\AI\DJANGO
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -TargetDir D:\AI\DJANGO -ZipPath .\exportfile_since_20260115_export_20260116.zip
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -TargetDir D:\AI\DJANGO -SinceTag 20260115

try { chcp 65001 | Out-Null } catch { }

$SCRIPT_ARGS = @($args)

function ArgKeyEquals([string]$a, [string]$b) {
  if ([string]::IsNullOrWhiteSpace($a) -or [string]::IsNullOrWhiteSpace($b)) { return $false }
  return [string]::Equals($a, $b, [System.StringComparison]::InvariantCultureIgnoreCase)
}

function Get-ArgValue([string]$name) {
  $alt = "/" + $name.TrimStart("-")
  for ($i=0; $i -lt $SCRIPT_ARGS.Count; $i++) {
    $k = [string]$SCRIPT_ARGS[$i]
    if ([string]::IsNullOrWhiteSpace($k)) { continue }
    if (ArgKeyEquals $k $name -or ArgKeyEquals $k $alt) {
      if (($i+1) -lt $SCRIPT_ARGS.Count) { return [string]$SCRIPT_ARGS[$i+1] }
    }
  }
  return $null
}

function Get-RelPath($Base, $Full) {
  if ($null -eq $Base -or $null -eq $Full) { return "" }
  if ($Full.Length -le $Base.Length) { return "" }
  $rel = $Full.Substring($Base.Length)
  return $rel.TrimStart('\','/')
}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

# TargetDir
$TargetDir = Get-ArgValue "-TargetDir"
if ([string]::IsNullOrEmpty($TargetDir)) {
  if ($SCRIPT_ARGS.Count -ge 1 -and $SCRIPT_ARGS[0] -notlike "-*" -and $SCRIPT_ARGS[0] -notlike "/*") {
    $TargetDir = [string]$SCRIPT_ARGS[0]
  }
}

# ZipPath / SinceTag / BackupDir
$ZipPath = Get-ArgValue "-ZipPath"
$SinceTag = Get-ArgValue "-SinceTag"
$BackupDir = Get-ArgValue "-BackupDir"

if ([string]::IsNullOrEmpty($TargetDir)) {
  Write-Host "ERROR: TargetDir missing."
  Write-Host "Run:"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\install.ps1 D:\AI\DJANGO"
  Write-Host "or:"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\install.ps1 -TargetDir D:\AI\DJANGO"
  exit 1
}

if ([string]::IsNullOrEmpty($BackupDir)) { $BackupDir = Join-Path $Here "backups" }
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

# -------------------------
# Pick zip if not specified
# -------------------------
if ([string]::IsNullOrEmpty($ZipPath)) {

  # 1) preferred pattern (new)
  $candidates = Get-ChildItem -Path $Here -Recurse -File |
    Where-Object { $_.Name -match '^exportfile_since_\d{8}_export_\d{8}\.zip$' }

  # 2) fallback pattern (old)
  if (-not $candidates -or $candidates.Count -eq 0) {
    $candidates = Get-ChildItem -Path $Here -Recurse -File |
      Where-Object { $_.Name -match '^exportfile_\d{8}\.zip$' }
  }

  # filter by -SinceTag if provided
  if (-not [string]::IsNullOrEmpty($SinceTag)) {
    $SinceTag = $SinceTag.Trim()
    $candidates = $candidates | Where-Object {
      $_.Name -match ('^exportfile_since_' + [regex]::Escape($SinceTag) + '_export_\d{8}\.zip$')
    }
  }

  $ZipPath = $candidates |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object { $_.FullName }
}

if ([string]::IsNullOrEmpty($ZipPath) -or -not (Test-Path $ZipPath)) {
  Write-Host "ERROR: export zip not found under (exportfile_since_YYYYMMDD_export_YYYYMMDD.zip or exportfile_YYYYMMDD.zip):"
  Write-Host ("  " + $Here)
  Write-Host "Tip 1: specify -ZipPath .\exportfile_since_YYYYMMDD_export_YYYYMMDD.zip"
  Write-Host "Tip 2: specify -SinceTag 20260115 to auto-pick latest zip for that since."
  exit 1
}

# -------------------------
# Extract / backup overwritten / apply
# -------------------------
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$TempDir = Join-Path $Here ("_tmp_extract_" + $ts)
$BackupStage = Join-Path $Here ("_tmp_backup_" + $ts)

if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
if (Test-Path $BackupStage) { Remove-Item $BackupStage -Recurse -Force }

New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
New-Item -ItemType Directory -Path $BackupStage -Force | Out-Null

Write-Host "============================================================"
Write-Host ("ZIP    : " + $ZipPath)
Write-Host ("TARGET : " + $TargetDir)
Write-Host ("BACKUP : " + $BackupDir)
Write-Host "============================================================"

Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force
$zipFiles = Get-ChildItem -Path $TempDir -Recurse -File

$overwriteCount = 0
foreach ($zf in $zipFiles) {
  $rel = Get-RelPath $TempDir $zf.FullName
  $targetFile = Join-Path $TargetDir $rel

  if (Test-Path $targetFile) {
    $overwriteCount++
    $backupFile = Join-Path $BackupStage $rel
    $backupDir2 = Split-Path $backupFile -Parent
    New-Item -ItemType Directory -Path $backupDir2 -Force | Out-Null
    Copy-Item -LiteralPath $targetFile -Destination $backupFile -Force
  }
}

if ($overwriteCount -gt 0) {
  $BackupZip = Join-Path $BackupDir ("backup_" + $ts + ".zip")
  if (Test-Path $BackupZip) { Remove-Item $BackupZip -Force }
  Compress-Archive -Path (Join-Path $BackupStage "*") -DestinationPath $BackupZip -Force
  Write-Host ("Backed up overwritten files: " + $overwriteCount)
  Write-Host ("Backup zip: " + $BackupZip)
} else {
  Write-Host "No files will be overwritten. No backup created."
}

foreach ($zf in $zipFiles) {
  $rel = Get-RelPath $TempDir $zf.FullName
  $dest = Join-Path $TargetDir $rel
  $destDir = Split-Path $dest -Parent
  New-Item -ItemType Directory -Path $destDir -Force | Out-Null
  Copy-Item -LiteralPath $zf.FullName -Destination $dest -Force
}

Write-Host ("Update applied to: " + $TargetDir)

Remove-Item $TempDir -Recurse -Force
Remove-Item $BackupStage -Recurse -Force

Write-Host "Done."
'@

$installContent | Out-File -FilePath $InstallPath -Encoding utf8

# -------------------------
# final bundle zip (3 files)
# -------------------------
$BundleTag = (Get-Date).ToString('MMdd_HHmm')
$BundleName = "exportfile_${BundleTag}.ZIP"
$BundlePath = Join-Path $OutDir $BundleName
$BundleStage = Join-Path $OutDir ("bundle_stage_" + $BundleTag + "_" + [guid]::NewGuid().ToString('N').Substring(0,8))

if (Test-Path $BundleStage) { Remove-Item $BundleStage -Recurse -Force }
New-Item -ItemType Directory -Path $BundleStage -Force | Out-Null

Copy-Item -LiteralPath $ZipPath -Destination (Join-Path $BundleStage (Split-Path $ZipPath -Leaf)) -Force
Copy-Item -LiteralPath $ListPath -Destination (Join-Path $BundleStage (Split-Path $ListPath -Leaf)) -Force
Copy-Item -LiteralPath $InstallPath -Destination (Join-Path $BundleStage (Split-Path $InstallPath -Leaf)) -Force

if (Test-Path $BundlePath) { Remove-Item $BundlePath -Force }
Compress-Archive -Path (Join-Path $BundleStage '*') -DestinationPath $BundlePath -Force

try { Remove-Item $BundleStage -Recurse -Force } catch { }

# remove intermediate 3 files after final bundle is created
if (Test-Path $BundlePath) {
  try { if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force } } catch { }
  try { if (Test-Path $ListPath) { Remove-Item $ListPath -Force } } catch { }
  try { if (Test-Path $InstallPath) { Remove-Item $InstallPath -Force } } catch { }
}

Write-Host "Export completed:"
Write-Host (" - BASE : " + $BasePath)
Write-Host (" - SINCE: " + $SinceDate.ToString("yyyy-MM-dd 00:00:00"))
Write-Host (" - LIST : " + $ListPath)
Write-Host (" - ZIP  : " + $ZipPath)
Write-Host (" - INST : " + $InstallPath)
Write-Host (" - FINAL: " + $BundlePath)
Write-Host ""
Write-Host "Import on another PC (recommended):"
Write-Host ("  1) unzip: " + $BundleName)
Write-Host "  2) run install.ps1 from extracted folder:"
Write-Host "     powershell -ExecutionPolicy Bypass -File .\install.ps1 D:\AI\DJANGO"




# -----------------------------
# args-only parsing (NO param)
# Supported:
#   .\export_since.ps1 20260101
#   .\export_since.ps1 2026-01-01
#   .\export_since.ps1 -Since 2026-01-01
#   .\export_since.ps1 -BasePath H:\AI\DJANGO -Since 2026-01-01
#匯出 powershell -ExecutionPolicy Bypass -File H:\AI\DJANGO\export_since.ps1  -BasePath H:\AI\DJANGO  -Since 2026-01-01
      # 會產生：
      # H:\AI\DJANGO\export_out\exportfile_YYYYMMDD.zip
      # H:\AI\DJANGO\export_out\filestru.txt
      # H:\AI\DJANGO\export_out\install.ps1
      # 匯入（另一台電腦）
      # 把 export_out 整個資料夾帶過去，進去後：
#匯入 powershell -ExecutionPolicy Bypass -File D:\AI\DJANGO\export_out\install.ps1 -TargetDir D:\AI\DJANGO -ZipPath D:\AI\DJANGO\export_out\exportfile_since_20260115_export_20260116.zip
