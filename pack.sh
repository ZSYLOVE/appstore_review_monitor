#!/bin/bash
# 打包给同事用的 zip（不含 app_data 密钥与配置）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NAME="appstore_review_monitor"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$(dirname "$ROOT")'); from appstore_review_monitor import __version__; print(__version__)" 2>/dev/null || echo "unknown")"
OUT="${ROOT}/../${NAME}-v${VERSION}.zip"

cd "$(dirname "$ROOT")"
rm -f "$OUT"
zip -r "$OUT" "$NAME" \
  -x "$NAME/app_data/*" \
  -x "$NAME/.git/*" \
  -x "$NAME/.update_backup/*" \
  -x "$NAME/__pycache__/*" \
  -x "$NAME/**/__pycache__/*" \
  -x "$NAME/.DS_Store" \
  -x "$NAME/**/.DS_Store" \
  -x "$NAME/.monitor.lock" \
  -x "$NAME/app_data/.monitor.lock"

echo "✅ 已生成: $OUT"
echo "   同事解压后运行: python3 check_app_status.py"
echo "   已内置 UPDATE_REPO，启动可自动检测更新"
