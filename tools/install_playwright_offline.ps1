Param(
  [string]$WheelDir = "H:\AI\whl",
  [string]$BrowsersDir = "H:\AI\pw-browsers"
)

Write-Host "[1/3] Install Playwright wheels from: $WheelDir"
python -m pip install --no-index --find-links "$WheelDir" playwright==1.45.0 pyee==11.1.0 greenlet==3.0.3
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "[2/3] Set Playwright browsers path: $BrowsersDir"
$env:PLAYWRIGHT_BROWSERS_PATH = $BrowsersDir

Write-Host "[3/3] Verify Playwright import"
python - << 'PY'
from playwright.sync_api import sync_playwright
print("playwright ok")
PY

Write-Host "Done."

# F:\AI\AI_TOOLS\venv3.12\Scripts\python.exe F:\AI\AI_TOOLS\tools\playwright_mock_from_json.py --json F:\AI\AI_TOOLS\SQLTEST_output1150001261.json --url http://127.0.0.1/djangoai/doc/
