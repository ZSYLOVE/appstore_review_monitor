#!/bin/bash
set -euo pipefail

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LAUNCHER_DIR")"

echo "App Store Review Monitor - 单次检查"
echo "项目目录: $PROJECT_DIR"
echo

cd "$PROJECT_DIR"
caffeinate -i -s python3 check_app_status.py --check-once

echo
read -r -p "单次检查完成。按回车关闭窗口..."

