# NutriLens（食鉴）部署到腾讯云 · 傻瓜教程（Nginx 版）

一套前后端分离的食物识别应用：上传/拍摄食物照片，识别菜品、营养与建议（Vue 3 + Vite + TypeScript 前端，FastAPI + SQLAlchemy + SQLite 后端，多模态大模型走 OpenAI 兼容接口）。本教程带你把项目部署到腾讯云服务器，对外用 `http://<你的公网IP>`（或绑域名后 `https://域名`）直接访问。

> 你是 Windows 本地开发，服务器是 Linux（Ubuntu 22.04 / 24.04）。所有服务器命令在 Linux 终端里执行。
> 与 day04（ScriptQuest）的差异：本项目后端端口是 **8010**（不是 8000）、环境变量前缀是 **`LLM_*`**、数据库落在 **`backend/.runtime/nutrilens.db`**、前端开发端口 5183。其余部署链路一致。
>
> **本版用 Nginx** 做反向代理 + 静态托管（day04 用 Caddy；这台腾讯云所在区域拉不到 Caddy 的 GPG 签名密钥源，故改用 Nginx，效果等价：静态托管 + `/api` 反代 + SSE 关缓冲 + SPA 回退）。

---

## 0. 先看这 5 个坑（看完少走 2 小时弯路）

| # | 坑 | 现象 | 本教程怎么解决 |
| - | --- | --- | --- |
| 1 | **`.env` 不能进仓库** | 里面有 DashScope API Key，push 出去就泄露 | `.gitignore` 已排除 `.env`，服务器上**手动创建** |
| 2 | **前端 `/api` 在生产环境没有代理** | 页面能打开，但所有接口、识别进度、流式对话全挂 | 用 Nginx 反代 `/api` → `127.0.0.1:8010` |
| 3 | **SSE 流被缓冲** | 识别进度/对话逐字要等很久才一次性吐出来 | Nginx `proxy_buffering off` 关缓冲，实时推 |
| 4 | **`--reload` 不能上生产** | 开发热重载多进程会弄坏 SSE 流 | 用 `uvicorn` 直起，`workers=1` |
| 5 | **`.venv` 解释器缺执行位（权限坑）** | 后端起不来，`Permission denied` | service 以 **root** 运行，绕过脆弱权限链（详见第 9 节） |

记住一句话：**开发用 Vite 代理，生产用 Nginx 代理，本质是同一件事——把 `/api` 转到后端 8010 端口。** 前端生产构建是同源的 `http://<IP>/api`，所以浏览器看到的是同源请求，连跨域都不触发（CORS 只是兜底）。

---

## 1. 第一步：把项目提交到 Git

> 当前目录还**不是 git 仓库**，先初始化。PowerShell / Git Bash / 终端都行。

```bash
cd D:/103/vibe_coding/day_05

git init
git add .
git status        # ★ 关键：确认列表里【没有】.env、.runtime、.venv、node_modules、dist
git commit -m "chore: initial commit NutriLens"
```

`git status` 必须**看不到**以下文件（它们已被 `.gitignore` 排除，正常不会出现）：

```
.env                    # 含密钥，绝不进仓库（注意是 backend/.env）
backend/.runtime/       # 本地 SQLite 库，服务器会自己建
backend/.venv/          # Python 虚拟环境
frontend/node_modules/  # 依赖
frontend/dist/          # 构建产物
```

把 `.env.example`（已进仓库，安全）当作模板即可。

### 推到远程仓库（用于以后 GitHub Actions 自动部署）

随便选一个：GitHub、Gitee（码云，国内快）、或腾讯云 CODING。新建一个**私有**仓库。

**推荐用 SSH 地址**（`git@...`）：服务器上 `git pull` 更新代码时不用输用户名密码。

```bash
git branch -M main
git remote add origin git@github.com:你的用户名/仓库名.git
git push -u origin main
```

> 之后每次改完代码：`git add . && git commit -m "..." && git push`。

---

## 2. 第二步：准备腾讯云服务器

### 2.1 买机器（推荐「轻量应用服务器」）

- 产品：**轻量应用服务器 Lighthouse**（比 CVM 便宜、控制台自带防火墙）
- 镜像：**Ubuntu 22.04 / 24.04 LTS**
- 配置：**2 核 2G 起步，预算够上 2 核 4G**（图片识别会临时吃内存）
- 地域：选离你近的（如上海/南京）

### 2.2 开防火墙端口

在轻量服务器控制台的「防火墙」里，**允许**以下规则（入站）：

| 应用 | 协议 | 端口 | 说明 |
| --- | --- | --- | --- |
| SSH | TCP | 22 | 远程登录（默认已开） |
| HTTP | TCP | 80 | 网站访问（必须开） |
| HTTPS | TCP | 443 | 可选；绑域名 + HTTPS 时才需要 |

> 如果你用的是 CVM（云服务器），则是在「安全组」里放通同样端口。

### 2.3 登录服务器

控制台点「登录」可直接用浏览器 WebShell；本地也行：

```bash
ssh ubuntu@<你的公网IP>      # 密码在控制台设置/重置
```

进去后先更新系统：

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 3. 第三步：装环境（Python / Node / Nginx / Git）

服务器上逐个执行：

```bash
# 基础工具
sudo apt install -y git curl ca-certificates gnupg

# Node.js 20（前端构建用）。用 NodeSource 官方源
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v && npm -v      # 期望 Node 18+ / npm 9+
# 国内加速：npm 镜像
sudo npm config set registry https://registry.npmmirror.com

# Nginx（反向代理 + 静态托管）
sudo apt install -y nginx
```

安装 Python（推荐用 **uv**，本地也在用，一条命令装好 3.11，不折腾系统 Python 版本）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

# uv 安装程序会把 uv 加到 ~/.bashrc，但当前 shell 还读不到。立刻生效：
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
uv --version             # 看到版本号才算装好

uv python install 3.11   # uv 自动下载 Python 3.11
```

> 如果 `uv --version` 还报 `command not found`，先检查它到底装在哪：`ls ~/.cargo/bin/uv ~/.local/bin/uv 2>/dev/null`

---

## 4. 第四步：拉代码 + 部署后端

约定服务器目录为 `/home/ubuntu/nutrilens`（和教程里的配置文件路径一致）。

### 4.1 拉代码（Git 方式）

```bash
cd /home/ubuntu
git clone git@github.com:你的用户名/仓库名.git nutrilens
cd nutrilens
```

> **本次实测用的是「tarball 直传」方式**（见文末附 A），因为当时还没配 Git 远程仓库。两种方式二选一，结果一致。

### 4.2 建 Python 虚拟环境并装依赖（国内镜像加速）

```bash
cd /home/ubuntu/nutrilens/backend
uv venv --python 3.11
export UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/
uv pip install -r requirements.txt
```

### 4.3 在服务器上创建 `.env`（★ 这步不能省）

仓库里只有 `backend/.env.example`，**密钥不会随 git 过来**。复制模板再填真实 Key：

```bash
cp /home/ubuntu/nutrilens/backend/.env.example /home/ubuntu/nutrilens/backend/.env
nano /home/ubuntu/nutrilens/backend/.env        # 把 LLM_API_KEY 改成你的真实 key
```

最小可用配置（`/home/ubuntu/nutrilens/backend/.env`）：

```ini
# --- 跨域：生产前端由 Nginx 同源托管，这里填服务器公网 IP / 域名兜底 ---
CORS_ORIGINS=http://<你的公网IP>

# --- 应用 ---
DEBUG=false
BACKEND_PORT=8010

# --- 大模型（OpenAI 兼容接口，默认已指向阿里云百炼 DashScope）---
# auto           = 有 KEY 走真实接口，没有则自动降级到内置 Mock（演示模式，仍可跑通）
# openai_compat  = 强制真实接口（无 KEY 直接报错）
# mock           = 强制离线 Mock，用于无网络演示与前端联调
LLM_PROVIDER=auto
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-vl-max-latest
LLM_API_KEY=sk-你的真实key

LLM_ENABLE_THINKING=false
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
LLM_TIMEOUT_SECONDS=60
```

> **没 Key 也能先部署**：把 `LLM_API_KEY` 留空（或 `LLM_PROVIDER=mock`），后端会自动进入「演示模式」，返回内置示例数据，页面顶部显示「演示模式」横幅。先把整条链路跑通，再回来填真实 Key 重启即可。
>
> 数据库用默认的 SQLite（`backend/.runtime/nutrilens.db`），**首次启动由 `init_db()` 自动建库**，不用手动建。

### 4.4 用 systemd 把后端跑成常驻服务

把本仓库 `deploy/nutrilens.service` 复制到系统目录：

```bash
sudo cp /home/ubuntu/nutrilens/deploy/nutrilens.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nutrilens
sudo systemctl status nutrilens      # 看到 active (running) 就对了
```

查看日志（排错用）：

```bash
journalctl -u nutrilens -f
```

本地先验证后端通不通（服务器内）：

```bash
curl http://127.0.0.1:8010/api/health
# 期望返回包含 "status":"ok" 的 JSON
```

---

## 5. 第五步：构建前端

```bash
cd /home/ubuntu/nutrilens/frontend
npm install
npm run build        # 产物在 frontend/dist/
```

确认产物生成：

```bash
ls /home/ubuntu/nutrilens/frontend/dist/index.html   # 应该存在
```

> **前端怎么知道后端地址？** 生产构建时 `VITE_API_BASE` 保持空，`client.ts` 会请求同源的 `/api`，由 Nginx 反代到 8010。
>
> **重要权限**：Nginx 以 `www-data` 用户运行，必须能遍历到 `/home/ubuntu/nutrilens/frontend/dist`。Ubuntu 主目录默认 `750`，会导致 Nginx 403，所以提前放行：
>
> ```bash
> sudo chmod 755 /home/ubuntu
> ```
> 只放开「进入目录」权限，不会暴露 `.ssh`、`.bash_history` 等文件内容。

---

## 6. 第六步：Nginx 反代（让网站和接口同域名）

把本仓库 `deploy/nutrilens.nginx` 复制为站点配置并启用：

```bash
sudo cp /home/ubuntu/nutrilens/deploy/nutrilens.nginx /etc/nginx/sites-available/nutrilens
sudo ln -sf /etc/nginx/sites-available/nutrilens /etc/nginx/sites-enabled/nutrilens
sudo rm -f /etc/nginx/sites-enabled/default      # 禁用默认站点，避免冲突
sudo nginx -t                                   # 测试配置语法
sudo systemctl enable --now nginx               # 启动并设置开机自启
```

Nginx 在这里干了三件事：

1. 把 `/` 指向 `frontend/dist/` 的静态文件（Vue 单页应用，含 SPA 路由回退）；
2. 把 `/api/`（以及 `/docs`、`/openapi.json`）转发到后端 `127.0.0.1:8010`；
3. `proxy_buffering off` **关掉缓冲**，SSE 实时推到浏览器（识别进度、对话逐字）。

> 改完 `nutrilens.nginx` 后执行 `sudo nginx -t && sudo systemctl reload nginx` 即可生效，不用重启。

---

## 7. 第七步：访问验证

浏览器打开 `http://<你的公网IP>`（不带端口，默认 80）。

- 能看到「食鉴 NutriLens」五个页面（识别/对话/历史/画像/关于） → 基础链路通了。
- 在「识别」页上传一张食物照片，能看到识别进度/结果卡实时返回 → SSE 正常。
- 接口文档：`http://<公网IP>/docs`（FastAPI Swagger）。

健康检查：

```bash
curl http://<公网IP>/api/health      # 经 Nginx 也应返回 ok
```

---

## 8. 以后怎么更新（一键脚本）

每次本地改完并 `git push` 后，在服务器上执行本仓库的 `deploy/update.sh`：

```bash
cd /home/ubuntu/nutrilens
bash deploy/update.sh
```

脚本会自动：拉最新代码 → 重新构建前端 → 更新后端依赖 → 重启后端服务。Nginx 不用动（它直接从磁盘读最新的 `dist/` 文件）。

你也可以手动分步：

```bash
cd /home/ubuntu/nutrilens && git pull
cd frontend && npm install && npm run build
sudo systemctl restart nutrilens
```

---

## 9. 常见问题排错

| 症状 | 原因 | 解决 |
| --- | --- | --- |
| 页面能开，但所有接口 404/连不上 | Nginx 没反代 `/api` | 检查站点已启用：`ls -l /etc/nginx/sites-enabled/nutrilens`；`sudo nginx -t && sudo systemctl reload nginx` |
| 识别进度/对话逐字一次性蹦出来，不实时 | SSE 被缓冲 | 确认 `nutrilens.nginx` 的 `/api/` 块里有 `proxy_buffering off;`，然后 `sudo systemctl reload nginx` |
| **后端起不来，反复 `Permission denied`** | `uv venv` 在该服务器上创建的解释器缺执行位（umask 偏严） | 已经让 service 以 **root** 运行绕过；若想用 `ubuntu` 用户，需 `chmod -R a+rx /home/ubuntu/nutrilens/backend/.venv`（含 `lib/` 下的真实解释器） |
| `/docs` 能访问，但根路径 `http://IP` 403 | `/home/ubuntu` 目录权限不足（Nginx 进不去） | `sudo chmod 755 /home/ubuntu && sudo systemctl reload nginx` |
| `/api/health` 返回 `demo_mode:true` | `.env` 里 `LLM_API_KEY` 空 | 正常（演示模式）；要真实识别就填 Key 重启 `sudo systemctl restart nutrilens` |
| 后端日志报 `Address already in use` | 8010 被别的进程占了 | `sudo ss -ltnp | grep :8010` 找到 PID，确认是旧进程再停 |
| 80 端口访问超时 | 防火墙没开 80 | 回 2.2 步，控制台防火墙放通 TCP 80 |
| `git pull` 要密码 | 远程用的 HTTPS | 改用 SSH 地址：`git remote set-url origin git@...` |

---

## 10.（可选）绑域名 + HTTPS

1. 在域名解析里把 `A 记录` 指向服务器公网 IP。
2. 控制台防火墙再放通 **443**（和 80 一起）。
3. 用 `certbot` 申请免费证书，或手动在 `nutrilens.nginx` 里补 `listen 443 ssl;` + 证书路径。
4. 访问 `https://yourdomain.com`。

> 不想绑域名、只用 IP 也完全没问题，保持 80 端口块即可（HTTP 明文，内部演示足够）。

---

## 11.（可选）自动部署：GitHub 推送即上线

做到这一步，每次更新还要手动 SSH 进服务器跑 `update.sh`。用 **GitHub Actions** 可以让 `main` 分支一有推送就自动部署。整体链路：

```
你 push 到 main
   └─ GitHub Actions 触发（云端 runner）
        └─ SSH 登录腾讯云服务器（用 SERVER_SSH_KEY）
             └─ 执行 deploy/update.sh（pull → 构建 → 重启）
                  └─ 网站自动更新 ✅
```

### 11.1 准备一把「Actions 登录服务器」的密钥

```bash
# 在本地开发机生成一对新密钥（文件名自取）
ssh-keygen -t ed25519 -C "github-actions-deploy" -N "" -f github_actions_key

# 把公钥追加到服务器的 authorized_keys（在【服务器】上执行）
cat github_actions_key.pub >> ~/.ssh/authorized_keys
```

- `github_actions_key`（私钥）→ 填进 GitHub Secrets 的 `SERVER_SSH_KEY`。
- `github_actions_key.pub`（公钥）→ 已加入服务器的 `~/.ssh/authorized_keys`。

### 11.2 让 `systemctl restart` 免输密码

`update.sh` 里有 `sudo systemctl restart nutrilens`，自动部署没人输密码，需要放行这一条：

```bash
# 在【服务器】上执行
echo 'ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nutrilens, /usr/bin/systemctl daemon-reload' | sudo tee /etc/sudoers.d/nutrilens
sudo chmod 440 /etc/sudoers.d/nutrilens
```

### 11.3 在 GitHub 加 Secrets

仓库 → **Settings → Secrets and variables → Actions → New repository secret**，添加三项：

| Secret 名 | 值 |
| --- | --- |
| `SERVER_HOST` | 服务器公网 IP |
| `SERVER_USER` | `ubuntu` |
| `SERVER_SSH_KEY` | `github_actions_key` 私钥的**全部内容**（含 `-----BEGIN/END-----` 那几行） |

### 11.4 提交 workflow 文件

本仓库已带 `.github/workflows/deploy.yml`。提交并推送到 `main`：

```bash
git add .github/workflows/deploy.yml deploy/update.sh deploy/nutrilens.service deploy/nutrilens.nginx
git commit -m "ci: auto deploy on push to main"
git push
```

推送后到仓库 **Actions** 标签页，能看到一次 `Deploy to Tencent Cloud` 运行；绿色 ✅ 就说明自动部署成功。以后你只管 `git push`，服务器会自动更新。

### 11.5 排错

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| Actions 红，报 `Permission denied (publickey)` | `SERVER_SSH_KEY` 不对 / 公钥没进服务器 `authorized_keys` | 重做 11.1，确认私钥完整、公钥已追加 |
| 部署成功但页面没变 | 浏览器缓存 / 构建没生效 | 硬刷新（Ctrl+F5）；看 Actions 日志确认 `npm run build` 跑过 |
| 前端类型检查失败导致部署中断 | `npm run build` 含 `vue-tsc` 类型检查 | 这是好事——别合有类型错误的代码；临时赶时间可改 `npm run build` 为 `npx vite build` |

---

## 附 A：本次实测用的「tarball 直传」部署（无 Git 远程时也行）

如果暂时没配 Git 远程仓库，可以用打包直传的方式（本次 day05 上线就是用这个）：

```powershell
# 本地 Windows：打包（排除 venv/node_modules/.runtime/dist/.env/.git）
cd D:/103/vibe_coding/day_05
tar -czf _nutrilens.tar.gz `
  --exclude='.git' --exclude='backend/.venv' --exclude='backend/.runtime' `
  --exclude='backend/__pycache__' --exclude='frontend/node_modules' --exclude='frontend/dist' `
  --exclude='backend/.env' .
```

然后把 `_nutrilens.tar.gz` 与 `backend/.env`（含真实 Key）用 scp / SFTP 传到服务器 `/tmp/`，在服务器上：

```bash
sudo mkdir -p /home/ubuntu/nutrilens
sudo tar -xzf /tmp/_nutrilens.tar.gz -C /home/ubuntu/nutrilens
sudo cp /tmp/nutrilens.server.env /home/ubuntu/nutrilens/backend/.env
sudo chown -R ubuntu:ubuntu /home/ubuntu/nutrilens
sudo chmod 755 /home/ubuntu
# 然后照第 4.2 / 4.4 / 5 / 6 步完成依赖、前端构建、service、Nginx 即可
```

> 注意：直传方式服务器上没有 git 仓库，`deploy/update.sh`（基于 `git pull`）会失效；要么改用上面的 Git 流程，要么以后更新时重新打包直传。

---

## 附 B：本教程配套文件

| 文件 | 作用 |
| --- | --- |
| `deploy/nutrilens.service` | systemd 后端常驻服务（uvicorn，端口 8010，workers=1，**root 运行**） |
| `deploy/nutrilens.nginx` | Nginx 站点：静态托管 + `/api` 反代 8010 + SSE 关缓冲 + SPA 回退 |
| `deploy/update.sh` | 一键拉代码、构建、重启（CI 里也调用它） |
| `.github/workflows/deploy.yml` | GitHub Actions：push 到 main 即自动 SSH 部署 |

> 路径都按 `/home/ubuntu/nutrilens` 写死。如果你把代码 clone 到别的目录，请同步改 `nutrilens.service`、`nutrilens.nginx`、`update.sh` 里的路径。
>
> 与 day04（ScriptQuest）的唯一实质差异：后端端口 **8010**、环境变量前缀 **`LLM_*`**、数据库位于 **`backend/.runtime/nutrilens.db`**；其余部署步骤可直接照搬 day04。
