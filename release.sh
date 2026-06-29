#!/bin/bash
# 发版助手：校验 __version__ 与 tag 一致，提交并推送到 GitHub
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INIT_PY="${ROOT}/__init__.py"
REPO="ZSYLOVE/appstore_review_monitor"

read_version() {
  python3 -c "
import re, pathlib
text = pathlib.Path('${INIT_PY}').read_text(encoding='utf-8')
m = re.search(r'__version__\s*=\s*[\"\\']([^\"\\']+)[\"\\']', text)
print(m.group(1) if m else '')
"
}

usage() {
  echo "用法: ./release.sh [版本号]"
  echo "示例: ./release.sh 2.1.5"
  echo ""
  echo "发版前请确认代码已测试通过。脚本会："
  echo "  1. 写入 __init__.py 的 __version__"
  echo "  2. git commit + tag + push"
  echo "  3. 提示去 GitHub 发布 Release（zip 同事靠这个自动更新）"
  exit 1
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage
[[ $# -gt 1 ]] && usage

TARGET="${1:-$(read_version)}"
[[ -z "${TARGET}" ]] && { echo "❌ 无法读取版本号，请传入: ./release.sh X.Y.Z"; exit 1; }

CURRENT="$(read_version)"
if [[ "${CURRENT}" != "${TARGET}" ]]; then
  echo "📝 更新 __init__.py: ${CURRENT:-未知} → ${TARGET}"
  python3 - <<PY
import re, pathlib
path = pathlib.Path("${INIT_PY}")
text = path.read_text(encoding="utf-8")
new = re.sub(
    r'(__version__\s*=\s*["\'])[^"\']+(["\'])',
    rf"\g<1>${TARGET}\g<2>",
    text,
    count=1,
)
path.write_text(new, encoding="utf-8")
PY
fi

echo ""
echo "📦 准备发版 v${TARGET}"
echo "   仓库: https://github.com/${REPO}"
echo ""

if ! git -C "${ROOT}" diff --quiet || ! git -C "${ROOT}" diff --cached --quiet; then
  git -C "${ROOT}" add -A
  git -C "${ROOT}" commit -m "v${TARGET}"
  echo "✅ 已提交"
else
  echo "ℹ️  工作区无变更，跳过 commit"
fi

if git -C "${ROOT}" rev-parse "v${TARGET}" >/dev/null 2>&1; then
  echo "⚠️  本地已有 tag v${TARGET}，跳过打 tag"
else
  git -C "${ROOT}" tag "v${TARGET}"
  echo "✅ 已打 tag v${TARGET}"
fi

echo ""
echo "🚀 推送到 GitHub …"
git -C "${ROOT}" push origin main --tags

echo ""
echo "─────────────────────────────────────────────"
echo "✅ 代码与 tag 已推送 v${TARGET}"
echo ""
echo "⚠️  还需一步（zip 同事自动更新必须）："
echo "   1. 打开 https://github.com/${REPO}/releases/new"
echo "   2. 选择 tag: v${TARGET}"
echo "   3. 点击 Publish release"
echo ""
echo "📌 更新机制说明："
echo "   · git clone 用户 → git pull（看 commit 是否落后）"
echo "   · zip 解压用户   → GitHub Release / raw 回退（无 .git）"
echo "   · app_data/ 配置与密钥不会被更新覆盖"
echo ""
echo "📦 新同事首次安装可运行: ./pack.sh"
echo "─────────────────────────────────────────────"
