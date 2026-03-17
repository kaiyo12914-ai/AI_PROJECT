你真正要的規範其實是：

一般頁面（各子系統內部頁）：一律用 {% url %}（因為 url name 必須存在，錯了就該立刻爆出來修）

Portal 入口頁（全站入口 / 目錄頁）：一律用 url_or（因為它要 fail-open，不能因某一個 app 沒掛好就整站入口掛掉）

我給你一段更「不會混淆」的版本，直接替換你那段註解即可：

{# ✅ 全站連結規範（避免混淆）
   1) 子系統內頁：一律用 {% url %} —— url name 不存在就應該立刻爆，方便開發期修正
   2) Portal 入口頁：一律用 {% url_or '/fallback/' 'url_name' %} —— 目錄頁必須 fail-open
      - 優先 reverse(url_name)
      - reverse 失敗才回 fallback_path（避免單一 app 未掛載導致整個入口頁渲染失敗）
   3) 反向代理前綴：由 settings.FORCE_SCRIPT_NAME 統一控制；reverse() 會自動帶前綴
#}


如果你希望再更「硬性」一點，我也可以幫你把 url_or 改成 只有在 settings.PORTAL_FAIL_OPEN=True 時才允許 fallback（其他頁面誤用就直接 raise），這樣就能徹底杜絕「到處用 url_or 逃避修 url name」的混亂。
下面給你一套「Django + IIS（ARR + URL Rewrite）反向代理」的標準解法（含 **/comment 前綴**、Django 設定、IIS 規則、常見錯誤排除與驗證方式）。照這套做，**最少改動、全站一致、不再漏前綴**。

---

## 目標架構（你目前的方案 A：前綴 comment）

外部（使用者看到）：

* `https://mpcai.mpc.mil.tw/comment/translator/`
* `https://mpcai.mpc.mil.tw/comment/doc/`
* `https://mpcai.mpc.mil.tw/comment/api/chat/`

內部（Django 服務）：

* `http://127.0.0.1:8000/translator/`
* `http://127.0.0.1:8000/doc/`
* `http://127.0.0.1:8000/api/chat/`

---

## IIS（ARR + URL Rewrite）必做設定

### 1) 先確認 ARR 當 Proxy

IIS 管理員 → Server → **Application Request Routing Cache** → **Server Proxy Settings**

* ✅ 勾選：**Enable Proxy**
* ✅（建議）Preserve client IP（依環境可做 XFF）

---

### 2) URL Rewrite 規則（/comment → 轉送到後端去掉前綴）

**Inbound Rule：CommentProxy**

* Pattern：`^comment/(.*)`
* Action（Rewrite）：

  * URL：`http://127.0.0.1:8000/{R:1}`
  * Append query string：✅
  * Stop processing of subsequent rules：✅

> 你前面寫 `http://mpcai.mpc.mil.tw:8000/{R:1}` 也行，但建議走 localhost/內網 IP（更穩、更快）。

---

### 3) 設定要送給 Django 的 Forwarded Headers（關鍵！）

在 **URL Rewrite → View Server Variables** 先新增允許寫入：

* `HTTP_X_FORWARDED_PROTO`
* `HTTP_X_FORWARDED_HOST`
* `HTTP_X_FORWARDED_PREFIX`
* `HTTP_X_FORWARDED_FOR`（可選）

然後在剛剛那條 Inbound Rule 底下加 **Server Variables**：

* `HTTP_X_FORWARDED_PROTO = https`
* `HTTP_X_FORWARDED_HOST = {HTTP_HOST}`
* `HTTP_X_FORWARDED_PREFIX = /comment`
* （可選）`HTTP_X_FORWARDED_FOR = {REMOTE_ADDR}` 或維持 ARR 既有

> **X_FORWARDED_PREFIX 最重要**：你漏前綴通常就是沒送這個，或 Django 沒統一使用。

---

## Django 必要設定（settings.py）

### 1) 讓 Django 正確辨識外部 https / host

```python
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

> 本機沒反向代理時，不要硬開 `SECURE_PROXY_SSL_HEADER` 也行；但上 IIS 時必開。

---

### 2) 統一「前綴」唯一真相（推薦做法）

你現在的症狀是：

> 正常應該是 `.../comment/translator -> .../comment/translator`
> 但變成 `.../translator -> .../translator`（漏 /comment）

要完全根治，**用 Django 官方機制**：`FORCE_SCRIPT_NAME`

```python
PROXY_PREFIX = env_str("PROXY_PREFIX", "").strip()  # 例：/comment
FORCE_SCRIPT_NAME = PROXY_PREFIX or ""
```

* `FORCE_SCRIPT_NAME` 會讓 `reverse()` / `{% url %}` / `request.build_absolute_uri()` **全部自動帶前綴**
* 這是全站一致的「唯一真相」，比只在 middleware 計算 `request.proxy_prefix` 更不會漏。

> 你想要「全站統一避免混淆」：**就是 FORCE_SCRIPT_NAME**。

---

### 3) CSRF / Cookie 在子路徑下的設定（很常被忽略）

若你是走 `/comment/...`，建議：

```python
CSRF_TRUSTED_ORIGINS = [
    "https://mpcai.mpc.mil.tw",
]

SESSION_COOKIE_PATH = "/comment"
CSRF_COOKIE_PATH = "/comment"
```

> 如果你希望 `/comment` 與根目錄共用 cookie（通常不建議），才用 `/`。
> 但多數情境「掛在子路徑」就用同一路徑最乾淨。

---

### 4) Static/Media（避免 static 路徑錯）

如果 static 也要在 comment 底下：

```python
STATIC_URL = f"{FORCE_SCRIPT_NAME}/static/" if FORCE_SCRIPT_NAME else "/static/"
MEDIA_URL = f"{FORCE_SCRIPT_NAME}/media/" if FORCE_SCRIPT_NAME else "/media/"
```

---

## Middleware 統一（你要的「避免混淆」版本）

* **IIS 有送 `X_FORWARDED_PREFIX`**：Django 一定拿得到
* **Django reverse**：用 `FORCE_SCRIPT_NAME` 統一
* **前端手刻 URL / JS fetch**：用你 `request.proxy_prefix`（當 fallback）

你現有 `ForwardedPrefixMiddleware` 可保留（用來提供 `request.proxy_prefix` 給 template/JS），但「是否自動帶前綴」請交給 **FORCE_SCRIPT_NAME**。

---

## 你本機無反向代理怎麼跑？

### 本機純跑根目錄（最建議）

`.env`

```env
PROXY_PREFIX=
USE_X_FORWARDED_HOST=0
SECURE_PROXY_SSL_VALUE=
```

### 本機要模擬 /comment（可用）

`.env`

```env
PROXY_PREFIX=/comment
USE_X_FORWARDED_HOST=0
SECURE_PROXY_SSL_VALUE=
```

> 本機沒 proxy 不要硬設 `SECURE_PROXY_SSL_VALUE=https`，不然 Django 會以為是 https 但實際是 http，可能引出 cookie/redirect 問題。

---

## 驗證（你要如何確認反向代理正確）

### 1) 用瀏覽器/DevTools 看 response header / redirect

* 打 `https://mpcai.mpc.mil.tw/comment/`
* 看有沒有被 302 到 `/comment/...`（**不應該掉到 `/...`**）

### 2) Django log 印出（非常有效）

在某個 view 暫時印：

* `request.path`
* `request.get_full_path()`
* `request.META.get("HTTP_X_FORWARDED_PREFIX")`
* `request.META.get("HTTP_X_FORWARDED_PROTO")`
* `request.META.get("HTTP_HOST")`

你會立刻知道是 IIS 沒送、還是 Django 沒吃。

---

## 你現在遇到的 NoReverseMatch（doc_page 找不到）

這不是 proxy 本身問題，是 **URL name 不存在**（或 include namespace 不對）。

你的 `url_or` tag 會 reverse，失敗才 fallback，但現在錯誤顯示是 template render 直接爆掉，代表你可能還有直接 `{% url 'doc_page' %}` 的地方或某段沒包好。

解法方向：

1. 全站統一：只用 `{% url_or '/doc/' 'doc_page' %}`
2. 或把 `webapps/doc/urls.py` 補上 name，例如：

   * `path("", views.index, name="doc_page")`

---

## 最小可行「一鍵穩定」配置總結

### IIS

* Rewrite：`^comment/(.*)` → `http://127.0.0.1:8000/{R:1}`
* 加 Server Variables：

  * `X-Forwarded-Proto=https`
  * `X-Forwarded-Host={HTTP_HOST}`
  * `X-Forwarded-Prefix=/comment`

### Django settings

* `USE_X_FORWARDED_HOST=True`
* `SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")`
* `FORCE_SCRIPT_NAME=/comment`（由 `.env PROXY_PREFIX` 帶入）
* `SESSION_COOKIE_PATH=/comment`
* `CSRF_COOKIE_PATH=/comment`
* `CSRF_TRUSTED_ORIGINS=["https://mpcai.mpc.mil.tw"]`
* `STATIC_URL=/comment/static/`（若 static 也要走 proxy）

---

如果你願意貼出 **IIS URL Rewrite 規則 XML（web.config）** 或截圖「Inbound Rules + Server Variables」那一頁，我可以直接幫你檢查是哪個欄位漏了，並給你可直接貼上的 web.config 範本。
