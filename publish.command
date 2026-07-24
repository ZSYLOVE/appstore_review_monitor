#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PUBLISH_SCRIPT="${SCRIPT_DIR}/publish.sh"

echo "App Store Review Monitor 发布工具"
echo "项目目录: ${SCRIPT_DIR}"
echo
echo "将自动执行:"
echo "  1. 当前版本最后一段按十进制 +1"
echo "  2. 检查 Python 语法"
echo "  3. 打包 zip"
echo "  4. git commit / tag / push"
echo "  5. 如缺少 gh，则尝试用 Homebrew 安装 gh"
echo "  6. 如 gh 已登录，则创建 GitHub Release 并上传 zip"
echo

if [[ ! -x "$PUBLISH_SCRIPT" ]]; then
  echo "错误: publish.sh 不存在或不可执行"
  echo "$PUBLISH_SCRIPT"
  echo
  read -r -p "按回车关闭窗口..."
  exit 1
fi

cd "$SCRIPT_DIR"
"$PUBLISH_SCRIPT" --install-gh

echo
read -r -p "发布脚本运行结束，按回车关闭窗口..."
