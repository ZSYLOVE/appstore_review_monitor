#!/bin/bash
# 一键发布脚本：自动递增版本、校验、打包、提交、打 tag、推送，并尽量自动创建 GitHub Release。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NAME="$(basename "$ROOT")"
INIT_PY="${ROOT}/__init__.py"
CONSTANTS_PY="${ROOT}/constants.py"
PARENT_DIR="$(dirname "$ROOT")"

VERSION=""
SKIP_TESTS=false
NO_PUSH=false
NO_RELEASE=false
DRY_RUN=false
INSTALL_GH=false

usage() {
  cat <<'EOF'
用法:
  ./publish.sh
  ./publish.sh 2.2.1
  ./publish.sh 2.2.1 --skip-tests
  ./publish.sh 2.2.1 --no-release
  ./publish.sh 2.2.1 --dry-run

参数:
  不传版本号     自动把当前版本最后一段按十进制 +1，例如 2.2.0 -> 2.2.1
  --skip-tests   跳过 Python 语法编译检查
  --install-gh   如果缺少 gh，并且已安装 Homebrew，则自动 brew install gh
  --no-push      不执行 git push
  --no-release   不创建 GitHub Release
  --dry-run      只打印将要执行的命令，不修改文件、不提交、不推送

发布内容:
  1. 写入 __init__.py 的 __version__
  2. Python compileall 语法检查
  3. 生成 ../appstore_review_monitor-vX.Y.Z.zip
  4. git add/commit/tag/push
  5. 如果安装并登录了 gh，则自动创建 GitHub Release 并上传 zip
EOF
}

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [[ "$DRY_RUN" != true ]]; then
    "$@"
  fi
}

die() {
  echo "❌ $*" >&2
  exit 1
}

read_version() {
  python3 - "$INIT_PY" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
print(match.group(1) if match else "")
PY
}

read_repo() {
  python3 - "$CONSTANTS_PY" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'DEFAULT_UPDATE_REPO\s*=\s*["\']([^"\']+)["\']', text)
print(match.group(1) if match else "")
PY
}

bump_version_decimal() {
  python3 - "$1" <<'PY'
import sys

version = sys.argv[1].strip()
parts = version.split(".")
if len(parts) < 2 or not all(part.isdigit() for part in parts):
    raise SystemExit(f"invalid version: {version}")
parts[-1] = str(int(parts[-1], 10) + 1)
print(".".join(parts))
PY
}

write_version() {
  local target="$1"

  if [[ "$DRY_RUN" == true ]]; then
    echo "+ update __version__ to ${target}"
    return
  fi

  python3 - "$INIT_PY" "$target" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
target = sys.argv[2]
text = path.read_text(encoding="utf-8")
new_text, count = re.subn(
    r'(__version__\s*=\s*["\'])[^"\']+(["\'])',
    rf"\g<1>{target}\g<2>",
    text,
    count=1,
)
if count != 1:
    raise SystemExit("cannot find __version__ in __init__.py")
path.write_text(new_text, encoding="utf-8")
PY
}

make_zip() {
  local version="$1"
  local out="${PARENT_DIR}/${NAME}-v${version}.zip"

  run rm -f "$out"
  (
    cd "$PARENT_DIR"
    run zip -r "$out" "$NAME" \
      -x "$NAME/app_data/*" \
      -x "$NAME/.git/*" \
      -x "$NAME/.update_backup/*" \
      -x "$NAME/__pycache__/*" \
      -x "$NAME/**/__pycache__/*" \
      -x "$NAME/.DS_Store" \
      -x "$NAME/**/.DS_Store" \
      -x "$NAME/.monitor.lock" \
      -x "$NAME/app_data/.monitor.lock"
  )

  echo "$out"
}

create_github_release() {
  local repo="$1"
  local version="$2"
  local zip_path="$3"
  local tag="v${version}"

  if [[ "$NO_RELEASE" == true ]]; then
    echo "ℹ️  已跳过 GitHub Release。"
    return
  fi

  if ! command -v gh >/dev/null 2>&1; then
    if [[ "$INSTALL_GH" == true ]]; then
      if command -v brew >/dev/null 2>&1; then
        echo "📥 未检测到 gh，正在通过 Homebrew 安装 GitHub CLI..."
        run brew install gh
      else
        echo "⚠️  未安装 GitHub CLI(gh)，且未检测到 Homebrew，无法自动安装。"
        echo "   可先安装 Homebrew 后运行: brew install gh"
        echo "   手动打开: https://github.com/${repo}/releases/new?tag=${tag}"
        echo "   上传文件: ${zip_path}"
        return
      fi
    fi
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "⚠️  未安装 GitHub CLI(gh)，无法自动创建 Release。"
    echo "   手动打开: https://github.com/${repo}/releases/new?tag=${tag}"
    echo "   上传文件: ${zip_path}"
    return
  fi

  if ! gh auth status >/dev/null 2>&1; then
    echo "⚠️  gh 未登录，无法自动创建 Release。先运行: gh auth login"
    echo "   手动打开: https://github.com/${repo}/releases/new?tag=${tag}"
    echo "   上传文件: ${zip_path}"
    return
  fi

  if gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
    run gh release upload "$tag" "$zip_path" --repo "$repo" --clobber
  else
    run gh release create "$tag" "$zip_path" \
      --repo "$repo" \
      --title "$tag" \
      --notes "Release ${tag}"
  fi
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    --install-gh)
      INSTALL_GH=true
      shift
      ;;
    --no-push)
      NO_PUSH=true
      shift
      ;;
    --no-release)
      NO_RELEASE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -*)
      die "未知参数: $1"
      ;;
    *)
      [[ -z "$VERSION" ]] || die "只能传一个版本号"
      VERSION="$1"
      shift
      ;;
  esac
done

REPO="$(read_repo)"
[[ -n "$REPO" ]] || die "无法从 constants.py 读取 DEFAULT_UPDATE_REPO"

CURRENT="$(read_version)"
[[ -n "$CURRENT" ]] || die "无法从 __init__.py 读取 __version__"

if [[ -z "$VERSION" ]]; then
  VERSION="$(bump_version_decimal "$CURRENT")"
  echo "🔢 自动递增版本: ${CURRENT} → ${VERSION}"
fi

[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || die "版本号格式不正确: $VERSION"

echo "─────────────────────────────────────────────"
echo "📦 发布 ${NAME}"
echo "   当前版本: ${CURRENT}"
echo "   目标版本: ${VERSION}"
echo "   仓库: https://github.com/${REPO}"
echo "   模式: $([[ "$DRY_RUN" == true ]] && echo DRY-RUN || echo RELEASE)"
echo "─────────────────────────────────────────────"

if git -C "$ROOT" rev-parse "v${VERSION}" >/dev/null 2>&1; then
  die "本地已存在 tag v${VERSION}"
fi

if git -C "$ROOT" ls-remote --exit-code --tags origin "v${VERSION}" >/dev/null 2>&1; then
  die "远程已存在 tag v${VERSION}"
fi

if [[ "$CURRENT" != "$VERSION" ]]; then
  echo "📝 更新版本号: ${CURRENT} → ${VERSION}"
  write_version "$VERSION"
fi

if [[ "$SKIP_TESTS" != true ]]; then
  echo "🧪 Python 语法检查..."
  run python3 -m compileall -q "$ROOT"
fi

echo "🗜️  打包 zip..."
ZIP_PATH="$(make_zip "$VERSION" | tail -n 1)"

echo "🧾 Git 提交..."
run git -C "$ROOT" add -A

if [[ "$DRY_RUN" != true ]]; then
  if ! git -C "$ROOT" diff --cached --quiet; then
    run git -C "$ROOT" commit -m "v${VERSION}"
  else
    echo "ℹ️  暂存区无变更，跳过 commit"
  fi
else
  echo "+ git -C ${ROOT} commit -m v${VERSION}"
fi

run git -C "$ROOT" tag "v${VERSION}"

if [[ "$NO_PUSH" == true ]]; then
  echo "ℹ️  已跳过 git push。"
else
  echo "🚀 推送代码和 tag..."
  run git -C "$ROOT" push origin main --tags
fi

create_github_release "$REPO" "$VERSION" "$ZIP_PATH"

echo ""
echo "─────────────────────────────────────────────"
echo "✅ 发布流程完成: v${VERSION}"
echo "   zip: ${ZIP_PATH}"
echo "   release: https://github.com/${REPO}/releases/tag/v${VERSION}"
echo "─────────────────────────────────────────────"
