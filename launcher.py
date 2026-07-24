import os
import stat
from textwrap import dedent

from .constants import PACKAGE_DIR


LAUNCHER_DIR = os.path.join(PACKAGE_DIR, "启动器")


LAUNCHERS = {
    "安装依赖.command": r'''#!/bin/bash
set -euo pipefail

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LAUNCHER_DIR")"

echo "App Store Review Monitor - 安装依赖"
echo "项目目录: $PROJECT_DIR"
echo

cd "$PROJECT_DIR"

caffeinate -i -s python3 - <<'PY'
import sys
import subprocess

try:
    import jwt
    wrong_jwt = not callable(getattr(jwt, "encode", None))
except ImportError:
    wrong_jwt = False

if wrong_jwt:
    print("检测到错误的 jwt 包，正在卸载...")
    subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "jwt"])
PY

caffeinate -i -s python3 -m pip install \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn \
  PyJWT cryptography curl_cffi PySocks psutil

caffeinate -i -s python3 - <<'PY'
import jwt
import cryptography
import curl_cffi
import socks
import psutil

assert callable(getattr(jwt, "encode", None)), "jwt 包不是 PyJWT"
print("依赖安装并验证完成。")
PY

echo
read -r -p "完成。按回车关闭窗口..."
''',
    "启动监控.command": r'''#!/bin/bash
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
''',
    "检查一次.command": r'''#!/bin/bash
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
''',
    "停止监控.command": r'''#!/bin/bash
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
''',
    "打开配置目录.command": r'''#!/bin/bash
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
''',
    "更新工具.command": r'''#!/bin/bash
set -euo pipefail

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LAUNCHER_DIR")"

echo "App Store Review Monitor - 检查并更新工具"
echo "项目目录: $PROJECT_DIR"
echo

cd "$PROJECT_DIR"
caffeinate -i -s python3 check_app_status.py --update

echo
read -r -p "更新流程结束。按回车关闭窗口..."
''',
}


def ensure_launchers() -> None:
    """Create or refresh user-facing macOS launchers after install/update."""
    os.makedirs(LAUNCHER_DIR, exist_ok=True)
    for filename, content in LAUNCHERS.items():
        path = os.path.join(LAUNCHER_DIR, filename)
        normalized = dedent(content).lstrip() + "\n"
        try:
            old = ""
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    old = f.read()
            if old != normalized:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(normalized)
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
