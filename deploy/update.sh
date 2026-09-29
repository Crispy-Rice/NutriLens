#!/usr/bin/env bash
# NutriLens 一键更新脚本：拉代码 -> 构建前端 -> 更新依赖 -> 重启后端
# 用法：bash /home/ubuntu/nutrilens/deploy/update.sh
#
# 设计要点（踩坑沉淀）：
# 1) 非交互 shell 下 uv / npm 可能不在 PATH，开头显式导出 PATH。
# 2) 首次部署（tarball 直传的目录无 .git）先 git init + 关联远程并强制 checkout，
#    之后每次更新用 reset --hard 保证工作区与 master 完全一致。
# 3) 拉代码后 exec 自身，避免"用旧脚本部署新代码"——只有脚本随代码更新时
#    才需要重跑一次，靠 REEXECED 环境变量防止无限循环。
set -e

# 非交互 shell 下确保 uv / node / npm 可用
export PATH="/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
# 若 node 装在 nvm 下，补充其 bin 路径（取最新版本目录）
for d in "$HOME/.nvm/versions/node"/*/bin; do
  [ -d "$d" ] && export PATH="$d:$PATH"
done

APP_DIR=/home/ubuntu/nutrilens

# ---- 防御：从 tarball 直传的目录可能没有 .git，先初始化为 git 仓库 ----
if [ ! -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR"
  git init -q
  git remote remove origin 2>/dev/null || true
  git remote add origin git@github.com:Crispy-Rice/NutriLens.git
  git fetch origin
  git checkout -f -B master origin/master
fi

cd "$APP_DIR"
# 拉取最新代码；reset --hard 保证工作区与远端 master 完全一致
git fetch origin
git reset --hard origin/master

# 脚本可能随仓库更新而变动，重新执行更新后的版本（仅一次）
if [ -z "$REEXECED" ]; then
  export REEXECED=1
  exec bash "$APP_DIR/deploy/update.sh"
fi

echo "==> 1/3 重新构建前端"
cd "$APP_DIR/frontend"
npm install
npm run build

echo "==> 2/3 更新后端依赖"
cd "$APP_DIR/backend"
# day05 的 .venv 由 uv 创建，内部不含 pip；必须用 uv 安装，否则会触发 PEP668
uv pip install --python .venv/bin/python -r requirements.txt

echo "==> 3/3 重启后端服务"
sudo systemctl restart nutrilens

echo "更新完成 ✅  访问 http://49.232.44.51/ 查看效果"
