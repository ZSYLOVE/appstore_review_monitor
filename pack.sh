#!/bin/bash
# 打包给同事用的 zip（不含 .git / app_data 密钥与配置）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NAME="appstore_review_monitor"
REPO="ZSYLOVE/appstore_review_monitor"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$(dirname "$ROOT")'); from appstore_review_monitor import __version__; print(__version__)" 2>/dev/null || echo "unknown")"
OUT="${ROOT}/../${NAME}-v${VERSION}.zip"

if [[ "${VERSION}" == "unknown" ]]; then
  echo "❌ 无法读取 __init__.py 中的 __version__"
  exit 1
fi

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

echo ""
echo "─────────────────────────────────────────────"
echo "✅ 已生成: ${OUT}"
echo "   版本: v${VERSION}"
echo ""
echo "👤 给新同事（首次安装）："
echo "   1. 解压 zip"
echo "   2. cd ${NAME}"
echo "   3. python3 check_app_status.py"
echo ""
echo "🔄 老同事（已安装过）："
echo "   启动程序时会自动检测更新，无需重新发 zip"
echo "   检测方式: GitHub Release → 失败时 raw 回退"
echo ""
echo "⚠️  发版者注意（zip 用户能自动更新必须做）："
echo "   · __init__.py 版本号 = git tag 名（如 v${VERSION}）"
echo "   · 推送后去 GitHub 发布 Release:"
echo "     https://github.com/${REPO}/releases/new"
echo "   · 推荐用 ./release.sh ${VERSION} 一键发版"
echo ""
echo "   zip 包不含 .git，同事走 Release 通道，不是 git pull"
echo "─────────────────────────────────────────────"
