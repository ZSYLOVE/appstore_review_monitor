#!/bin/bash
set -euo pipefail

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LAUNCHER_DIR")"

echo "App Store Review Monitor - 启动监控"
echo "项目目录: $PROJECT_DIR"
echo
echo "已启用 caffeinate，监控运行时会阻止 Mac 睡眠。"
echo

cd "$PROJECT_DIR"
caffeinate -i -s python3 check_app_status.py

echo
read -r -p "监控已结束。按回车关闭窗口..."

