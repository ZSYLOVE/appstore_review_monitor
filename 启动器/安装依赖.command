#!/bin/bash
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
