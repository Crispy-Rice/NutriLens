#!/usr/bin/env bash
# NutriLens 一键更新脚本：拉代码 -> 构建前端 -> 更新依赖 -> 重启后端
# 用法：cd /home/ubuntu/nutrilens && bash deploy/update.sh
set -e

APP_DIR=/home/ubuntu/nutrilens

echo "==> 1/4 拉取最新代码"
cd "$APP_DIR"
# 用 reset --hard 而不是 pull，保证工作区始终与 main 完全一致，
# 避免自动部署时本地有遗留改动导致合并冲突而中断。
git fetch origin
git reset --hard origin/main

echo "==> 2/4 重新构建前端"
cd "$APP_DIR/frontend"
npm install
npm run build

echo "==> 3/4 更新后端依赖"
cd "$APP_DIR/backend"
source .venv/bin/activate
pip install -r requirements.txt

echo "==> 4/4 重启后端服务"
sudo systemctl restart nutrilens

echo "更新完成 ✅  访问 http://<你的公网IP> 查看效果"
