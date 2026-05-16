# AI_TOOLS 開發環境與 Git 版本控管

## 1. 架構定案（GitHub 為唯一中樞）

```text
Git 中樞（雲端）
└── GitHub Repo（origin）

A 電腦 Windows
└── H:\AI\AI_TOOLS
    └── venv 或 .venv-win（不進 Git）

B 電腦 WSL Ubuntu
└── /mnt/d/AI/AI_TOOLS
    ├── venv（不進 Git）
    └── Hermes Agent + Docker
```

重點原則：
- Git 中樞改為 GitHub `origin`。
- A/B 只透過 `git pull` / `git push` 與 GitHub 同步。
- `.env` 不進 Git。
- `venv` / `.venv-win` 不進 Git。

## 2. GitHub 遠端設定（A 電腦）

### 2.1 新專案初始化

```powershell
cd H:\AI\AI_TOOLS
git init
git branch -M main
git remote add origin https://github.com/yuanlinwen-cell/Django.git

git add .
git commit -m "Initial commit"
git push -u origin main
```

### 2.2 已有 Git 專案改用 GitHub

```powershell
cd H:\AI\AI_TOOLS
git remote -v
git remote set-url origin https://github.com/yuanlinwen-cell/Django.git
git push -u origin main
```

## 3. A 電腦 venv（Windows）

### 3.1 沿用既有 venv

```powershell
cd H:\AI\AI_TOOLS
.\venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

### 3.2 建議命名（較清楚）

```powershell
cd H:\AI\AI_TOOLS
py -3 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 4. B 電腦 clone（WSL）

```bash
mkdir -p /mnt/d/AI
cd /mnt/d/AI
git clone https://github.com/yuanlinwen-cell/Django.git AI_TOOLS
cd AI_TOOLS
```

建立 B 的 venv：

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. 若 B 端資料夾已存在

### 5.1 直接接上 GitHub

```bash
cd /mnt/d/AI/AI_TOOLS
git init
git remote add origin https://github.com/yuanlinwen-cell/Django.git
git fetch origin
git checkout -b main origin/main
```

### 5.2 較安全做法：先備份再重 clone

```bash
mv /mnt/d/AI/AI_TOOLS /mnt/d/AI/AI_TOOLS_backup
mkdir -p /mnt/d/AI
cd /mnt/d/AI
git clone https://github.com/yuanlinwen-cell/Django.git AI_TOOLS
```

## 6. B 電腦 Hermes Agent 工作流程

```bash
cd /mnt/d/AI/AI_TOOLS
git pull --rebase origin main
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

## 7. A 電腦接收 Hermes 修改

```powershell
cd H:\AI\AI_TOOLS
git fetch origin
git checkout agent/hermes-task
```

確認後合併回 `main`：

```powershell
git checkout main
git pull --rebase origin main
git merge agent/hermes-task
git push origin main
```

## 8. `.gitignore` 必備設定

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

## 9. 建議加入 `.env.example`

```env
DEBUG=True
DJANGO_SECRET_KEY=
OPENAI_API_KEY=
ALLOWED_HOSTS=localhost,127.0.0.1
```

實際環境變數檔路徑：
- A：`H:\AI\AI_TOOLS\.env`
- B：`/mnt/d/AI/AI_TOOLS/.env`

## 10. 版本同步腳本使用說明（A/B 共用）

專案根目錄提供 4 支腳本：
- `git-sync.sh`：WSL/Linux 同步腳本
- `git-push.sh`：WSL/Linux 提交推送腳本
- `git-sync.ps1`：Windows PowerShell 同步腳本
- `git-push.ps1`：Windows PowerShell 提交推送腳本

### 10.1 WSL（`.sh`）

```bash
cd /mnt/d/AI/AI_TOOLS
bash git-sync.sh main
bash git-push.sh "feat: your message"
```

### 10.2 Windows（`.ps1`）

```powershell
cd H:\AI\AI_TOOLS
.\git-sync.ps1 -Branch main
.\git-push.ps1 -Message "feat: your message"
```

### 10.3 建議日常流程
- 開工前先同步：`git-sync`
- 開新功能分支：`git checkout -b feat/<topic>`
- 完成後提交推送：`git-push`
- 合併前再同步一次 `main`，降低衝突機率。

### 10.4 注意事項
- 若遇到 rebase 衝突：先解衝突，再 `git rebase --continue`。
- `.env`、`venv/`、`.venv-win/` 不可提交。
- A/B 版本一致以 GitHub `origin` 為準。

## 11. WSL 遠端錯誤快速修正

若出現 `origin = H:\git\AI_TOOLS.git`（Windows 路徑）導致 WSL 無法解析，請改成 GitHub：

```bash
cd /mnt/d/AI/AI_TOOLS
git remote set-url origin https://github.com/yuanlinwen-cell/Django.git
git remote -v
```

再執行：

```bash
bash git-sync.sh main
```

## 12. 結論

- Git 中樞固定為 GitHub，不再使用本機 `H:\git\AI_TOOLS.git` 當中樞。
- A/B 僅同步程式碼，不同步 `venv` 與 `.env`。
- AI 協助 commit 時，必須聯動執行 sync/push 腳本並回報結果。