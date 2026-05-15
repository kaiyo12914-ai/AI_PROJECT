# AI_TOOLS 開發環境管理手冊

## 1. 架構定案

```text
A 電腦 Windows
├── H:\git\AI_TOOLS.git       # Git 中樞 bare repo（不在此寫程式）
├── H:\AI\AI_TOOLS            # A 的 Windows 開發目錄
│   └── venv 或 .venv-win       # A 專用 venv（不進 Git）
└── 對 B 提供 Git 存取
    ├── 方式 1：Windows 網路分享
    └── 方式 2：SSH

B 電腦 WSL Ubuntu
└── /mnt/d/AI/AI_TOOLS          # B 的 WSL 開發目錄
    ├── venv                    # B 專用 venv（不進 Git）
    └── Hermes Agent + Docker
```

重點原則：
- `H:\git\AI_TOOLS.git` 是 Git 中樞，只做版本中繼。
- A/B 各自維護自己的 venv，不同步。
- `.env` 不進 Git。
- `venv` / `.venv-win` 不進 Git。

## 2. A 電腦建立 Git 中樞（bare repo）

在 A 的 Windows PowerShell：

```powershell
mkdir H:\git
git init --bare H:\git\AI_TOOLS.git
```

注意：
- 不要用 VS Code 開 `H:\git\AI_TOOLS.git`。

## 3. A 電腦把現有專案推入中樞

### 3.1 專案尚未初始化 Git

```powershell
cd H:\AI\AI_TOOLS

git init
git branch -M main
git remote add origin H:\git\AI_TOOLS.git

git add .
git commit -m "Initial commit"
git push -u origin main
```

### 3.2 專案已是 Git repo（改 remote）

```powershell
cd H:\AI\AI_TOOLS

git remote -v
git remote remove origin
git remote add origin H:\git\AI_TOOLS.git
git push -u origin main
```

## 4. A 電腦 venv（Windows）

### 4.1 沿用既有 venv

```powershell
cd H:\AI\AI_TOOLS
.\venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

### 4.2 建議命名（較清楚）

```powershell
cd H:\AI\AI_TOOLS
py -3 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 5. B 電腦透過網路分享存取 A 的 Git 中樞

A 電腦分享：
- 分享資料夾：`H:\git`
- 分享名稱：`git`（範例）
- A 電腦名稱：`A-PC`（範例）

在 B 的 WSL Ubuntu：

```bash
sudo mkdir -p /mnt/a_git
sudo mount -t drvfs '\\A-PC\git' /mnt/a_git
ls /mnt/a_git
```

預期可看到：`AI_TOOLS.git`

## 6. B 電腦 clone 到 `/mnt/d/AI/AI_TOOLS`

```bash
mkdir -p /mnt/d/AI
cd /mnt/d/AI

git clone /mnt/a_git/AI_TOOLS.git AI_TOOLS
cd AI_TOOLS
```

建立 B 的 venv：

```bash
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

若尚無 `requirements.txt`：

```bash
pip install django openai python-dotenv
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Add requirements"
git push
```

## 7. 若 B 端資料夾已存在

### 7.1 不覆蓋，直接接上 Git

```bash
cd /mnt/d/AI/AI_TOOLS
git init
git remote add origin /mnt/a_git/AI_TOOLS.git
git fetch origin
git checkout -b main origin/main
```

### 7.2 較安全做法：先備份再重 clone

```bash
mv /mnt/d/AI/AI_TOOLS /mnt/d/AI/AI_TOOLS_backup
mkdir -p /mnt/d/AI
cd /mnt/d/AI
git clone /mnt/a_git/AI_TOOLS.git AI_TOOLS
```

## 8. B 電腦 Hermes Agent 工作流程

```bash
cd /mnt/d/AI/AI_TOOLS
git pull
source venv/bin/activate
git checkout -b agent/hermes-task
```

啟動 Hermes Docker：

```bash
docker run -it --rm \
  -v ~/.hermes:/opt/data \
  -v /mnt/d/AI/AI_TOOLS:/workspace \
  -w /workspace \
  nousresearch/hermes-agent
```

修改後檢查：

```bash
git diff
python manage.py check
python manage.py test
```

提交推送：

```bash
git add .
git commit -m "Hermes agent update"
git push -u origin agent/hermes-task
```

## 9. A 電腦接收 Hermes 分支

```powershell
cd H:\AI\AI_TOOLS

git fetch
git checkout agent/hermes-task
```

確認後合併回 `main`：

```powershell
git checkout main
git pull
git merge agent/hermes-task
git push
```

## 10. `.gitignore` 必備設定

```gitignore
# Python
__pycache__/
*.py[cod]

# Django
db.sqlite3
*.sqlite3-journal
media/

# Env
.env
.env.*
!.env.example

# Virtual environments
venv/
.venv/
.venv-win/
venv_windows/
venv_old/

# OS
.DS_Store
Thumbs.db

# VS Code
.vscode/
```

必要結論：
- `venv/`、`.venv-win/`、`.env` 一律不可提交。

## 11. 建議加入 `.env.example`

```env
DEBUG=True
DJANGO_SECRET_KEY=
OPENAI_API_KEY=
ALLOWED_HOSTS=localhost,127.0.0.1
```

實際環境變數檔路徑：
- A：`H:\AI\AI_TOOLS\.env`
- B：`/mnt/d/AI/AI_TOOLS/.env`

## 12. 日常協作準則

- A/B 同步一律走 `git push` / `git pull`。
- 不同步 venv，不同步 `.env`。
- 功能開發用分支，驗證後再合併回 `main`。
- `H:\git\AI_TOOLS.git` 僅當中樞，不做開發。
## 13. 版本同步腳本使用說明（A/B 共用）

專案根目錄已提供 4 支腳本：

- `git-sync.sh`：WSL/Linux 同步腳本
- `git-push.sh`：WSL/Linux 提交推送腳本
- `git-sync.ps1`：Windows PowerShell 同步腳本
- `git-push.ps1`：Windows PowerShell 提交推送腳本

### 13.1 WSL（`.sh`）版本

先切到專案目錄：

```bash
cd /mnt/d/AI/AI_TOOLS
```

同步 `main`：

```bash
bash git-sync.sh main
```

提交並推送目前分支：

```bash
bash git-push.sh "feat: your message"
```

### 13.2 Windows（`.ps1`）版本

先切到專案目錄：

```powershell
cd H:\AI\AI_TOOLS
```

同步 `main`：

```powershell
.\git-sync.ps1 -Branch main
```

提交並推送目前分支：

```powershell
.\git-push.ps1 -Message "feat: your message"
```

### 13.3 建議日常流程

- 開工前先同步：
  - WSL：`bash git-sync.sh main`
  - Windows：`.\git-sync.ps1 -Branch main`
- 開新功能分支開發：`git checkout -b feat/<topic>`
- 完成後推送分支：
  - WSL：`bash git-push.sh "feat: ..."`
  - Windows：`.\git-push.ps1 -Message "feat: ..."`
- 合併前再同步一次 `main`，降低衝突機率。

### 13.4 注意事項

- 若遇到 rebase 衝突：先解衝突，再執行 `git rebase --continue`。
- `.env`、`venv/`、`.venv-win/` 不可提交。
- A/B 版本一致以 `origin`（`H:\git\AI_TOOLS.git`）為準。