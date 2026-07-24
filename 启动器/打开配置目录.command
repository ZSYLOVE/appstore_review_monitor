#!/bin/bash
set -euo pipefail

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LAUNCHER_DIR")"
APP_DATA_DIR="$PROJECT_DIR/app_data"

echo "App Store Review Monitor - 打开配置目录"
echo "配置目录: $APP_DATA_DIR"
echo

mkdir -p "$APP_DATA_DIR"
open "$APP_DATA_DIR"

echo "已在 Finder 中打开配置目录。"
echo
read -r -p "按回车关闭窗口..."

