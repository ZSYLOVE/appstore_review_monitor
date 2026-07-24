#!/bin/bash
set -euo pipefail

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LAUNCHER_DIR")"
LOCK_FILE="$PROJECT_DIR/app_data/.monitor.lock"

echo "App Store Review Monitor - 停止监控"
echo "项目目录: $PROJECT_DIR"
echo

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "没有找到监控锁文件，可能当前没有监控进程在运行。"
  echo
  read -r -p "按回车关闭窗口..."
  exit 0
fi

PID="$(cat "$LOCK_FILE" 2>/dev/null | tr -cd '0-9')"
if [[ -z "$PID" ]]; then
  echo "锁文件内容无效，已删除旧锁文件。"
  rm -f "$LOCK_FILE"
  echo
  read -r -p "按回车关闭窗口..."
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  echo "正在停止监控进程 PID: $PID"
  kill "$PID" 2>/dev/null || true
  sleep 1
  if kill -0 "$PID" 2>/dev/null; then
    echo "进程仍在运行，可手动执行: kill $PID"
  else
    echo "监控进程已停止。"
  fi
else
  echo "锁文件中的进程已不存在，删除旧锁文件。"
  rm -f "$LOCK_FILE"
fi

echo
read -r -p "完成。按回车关闭窗口..."
