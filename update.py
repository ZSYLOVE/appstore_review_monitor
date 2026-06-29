import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from typing import NamedTuple, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from . import __version__
from .constants import APP_DATA_DIR, CONFIG_FILE, DEFAULT_UPDATE_REPO, PACKAGE_DIR


class UpdateInfo(NamedTuple):
    available: bool
    local_version: str
    remote_version: str
    method: str  # git | github | gitee | none
    detail: str = ""


def parse_version(version: str) -> tuple:
    version = (version or "").strip().lstrip("vV")
    parts = []
    for piece in re.split(r"[.\-+]", version):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            break
    return tuple(parts) if parts else (0,)


def version_lt(left: str, right: str) -> bool:
    return parse_version(left) < parse_version(right)


def _read_update_repo() -> str:
    env_repo = os.environ.get("APPSTORE_MONITOR_UPDATE_REPO", "").strip()
    if env_repo:
        return env_repo
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            repo = (data.get("UPDATE_REPO") or "").strip()
            if repo:
                return repo
        except Exception:
            pass
    return DEFAULT_UPDATE_REPO


def _http_get_json(url: str, timeout: int = 15) -> dict:
    req = Request(url, headers={"User-Agent": "AppStoreMonitor-Updater", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, timeout: int = 15) -> str:
    req = Request(url, headers={"User-Agent": "AppStoreMonitor-Updater"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _fetch_remote_version_via_raw(repo: str) -> str:
    """从 raw.githubusercontent.com 读取远程 __init__.py，不消耗 GitHub API 配额。"""
    repo = repo.strip().strip("/")
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/__init__.py"
        try:
            version = _parse_version_from_init(_http_get_text(url))
            if version:
                return version
        except URLError:
            continue
    return ""


def _git_available() -> bool:
    return bool(shutil.which("git")) and os.path.isdir(os.path.join(PACKAGE_DIR, ".git"))


def _git_run(args, *, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=PACKAGE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _parse_version_from_init(content: str) -> str:
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else ""


def _read_local_version() -> str:
    init_path = os.path.join(PACKAGE_DIR, "__init__.py")
    try:
        with open(init_path, "r", encoding="utf-8") as f:
            version = _parse_version_from_init(f.read())
            if version:
                return version
    except Exception:
        pass
    return __version__


def _read_remote_init_version() -> str:
    for ref in ("origin/HEAD:__init__.py", "origin/main:__init__.py"):
        result = _git_run(["show", ref], timeout=20)
        if result.returncode == 0:
            version = _parse_version_from_init(result.stdout)
            if version:
                return version
    return ""


def _commits_behind_upstream() -> Optional[int]:
    behind = _git_run(["rev-list", "--count", "HEAD..@{u}"])
    if behind.returncode == 0 and behind.stdout.strip().isdigit():
        return int(behind.stdout.strip())
    return None


def _latest_git_tag() -> str:
    tag_result = _git_run(["tag", "-l", "--sort=-v:refname"])
    if tag_result.returncode != 0:
        return ""
    for line in tag_result.stdout.splitlines():
        tag = line.strip()
        if tag:
            return tag.lstrip("vV")
    return ""


def _check_git_update() -> Optional[UpdateInfo]:
    if not _git_available():
        return None

    local_version = _read_local_version()

    fetch = _git_run(["fetch", "--tags", "--quiet"], timeout=120)
    if fetch.returncode != 0:
        return UpdateInfo(False, local_version, local_version, "git", fetch.stderr.strip() or "git fetch 失败")

    remote_init_version = _read_remote_init_version()
    commits_behind = _commits_behind_upstream()

    # 已与远程同步：以 __init__.py 为准，避免 tag 与代码版本不一致导致重复更新
    if commits_behind is not None:
        if commits_behind == 0:
            remote_version = remote_init_version or local_version
            return UpdateInfo(False, local_version, remote_version, "git")
        remote_version = remote_init_version or _latest_git_tag() or "最新提交"
        return UpdateInfo(
            True,
            local_version,
            remote_version,
            "git",
            f"本地分支落后远程 {commits_behind} 个提交",
        )

    remote_version = remote_init_version or _latest_git_tag()
    if not remote_version:
        return UpdateInfo(False, local_version, local_version, "git", "无法获取远程版本")

    if version_lt(local_version, remote_version):
        return UpdateInfo(True, local_version, remote_version, "git")
    return UpdateInfo(False, local_version, remote_version, "git")


def _check_github_update(repo: str) -> Optional[UpdateInfo]:
    repo = repo.strip().strip("/")
    if not repo or "/" not in repo:
        return None

    local_version = _read_local_version()
    remote_version = ""
    detail = ""

    try:
        data = _http_get_json(f"https://api.github.com/repos/{repo}/releases/latest")
        if data.get("message"):
            detail = str(data.get("message", ""))
        else:
            tag = (data.get("tag_name") or data.get("name") or "").lstrip("vV")
            if tag:
                remote_version = tag
    except URLError as e:
        detail = str(e)

    if not remote_version:
        raw_version = _fetch_remote_version_via_raw(repo)
        if raw_version:
            remote_version = raw_version
        elif detail:
            return UpdateInfo(False, local_version, "未知", "github", detail)

    if not remote_version:
        return UpdateInfo(False, local_version, "未知", "github", "无法获取远程版本")

    if version_lt(local_version, remote_version):
        return UpdateInfo(True, local_version, remote_version, "github")
    return UpdateInfo(False, local_version, remote_version, "github")


def _check_gitee_update(repo: str) -> Optional[UpdateInfo]:
    repo = repo.strip().strip("/")
    if not repo or "/" not in repo:
        return None
    try:
        data = _http_get_json(f"https://gitee.com/api/v5/repos/{repo}/releases/latest")
    except URLError as e:
        return UpdateInfo(False, __version__, __version__, "gitee", str(e))

    tag = (data.get("tag_name") or data.get("name") or "").lstrip("vV")
    if not tag:
        return UpdateInfo(False, __version__, __version__, "gitee", "Release 无版本号")
    if version_lt(__version__, tag):
        return UpdateInfo(True, __version__, tag, "gitee")
    return UpdateInfo(False, __version__, tag, "gitee")


def check_for_update() -> UpdateInfo:
    git_info = _check_git_update()
    if git_info is not None:
        if git_info.available or git_info.method == "git":
            return git_info

    repo = _read_update_repo()
    if not repo:
        return UpdateInfo(False, __version__, __version__, "none", "未配置 UPDATE_REPO")

    if repo.startswith("gitee:"):
        gitee_info = _check_gitee_update(repo.split(":", 1)[1])
        return gitee_info or UpdateInfo(False, __version__, __version__, "none")

    github_info = _check_github_update(repo)
    return github_info or UpdateInfo(False, __version__, __version__, "none")


def _list_updatable_files(root: str) -> list:
    files = []
    for name in os.listdir(root):
        if name == "app_data" or name.startswith("."):
            continue
        path = os.path.join(root, name)
        if os.path.isfile(path) and name.endswith(".py"):
            files.append(name)
    return files


def _backup_code_files() -> str:
    backup_dir = os.path.join(PACKAGE_DIR, ".update_backup")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = str(int(os.path.getmtime(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else 0))
    target = os.path.join(backup_dir, stamp)
    os.makedirs(target, exist_ok=True)
    for name in _list_updatable_files(PACKAGE_DIR):
        shutil.copy2(os.path.join(PACKAGE_DIR, name), os.path.join(target, name))
    return target


def _restore_backup(backup_dir: str) -> None:
    for name in _list_updatable_files(backup_dir):
        shutil.copy2(os.path.join(backup_dir, name), os.path.join(PACKAGE_DIR, name))


def _apply_git_update() -> tuple:
    pull = _git_run(["pull", "--ff-only"], timeout=120)
    if pull.returncode == 0:
        return True, "git pull 成功"
    pull = _git_run(["pull", "--ff-only", "origin", "main"], timeout=120)
    if pull.returncode == 0:
        return True, "git pull origin main 成功"
    return False, (pull.stderr or pull.stdout or "git pull 失败").strip()


def _download_bytes(url: str, timeout: int = 120) -> bytes:
    req = Request(url, headers={"User-Agent": "AppStoreMonitor-Updater"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _apply_release_update(info: UpdateInfo) -> tuple:
    repo = _read_update_repo().strip()
    if repo.startswith("gitee:"):
        repo_path = repo.split(":", 1)[1].strip("/")
        zip_url = f"https://gitee.com/{repo_path}/repository/archive/{info.remote_version}.zip"
    else:
        repo_path = repo.strip("/")
        zip_url = f"https://github.com/{repo_path}/archive/refs/tags/v{info.remote_version}.zip"

    backup_dir = _backup_code_files()
    try:
        payload = _download_bytes(zip_url)
    except URLError as e:
        return False, f"下载更新包失败: {e}"

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "release.zip")
            with open(zip_path, "wb") as f:
                f.write(payload)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)

            extracted_root = None
            for name in os.listdir(tmp_dir):
                if name == "release.zip":
                    continue
                path = os.path.join(tmp_dir, name)
                if os.path.isdir(path):
                    extracted_root = path
                    break
            if not extracted_root:
                return False, "更新包结构异常"

            inner_root = extracted_root
            if len(_list_updatable_files(inner_root)) <= 1:
                for name in os.listdir(inner_root):
                    nested = os.path.join(inner_root, name)
                    if os.path.isdir(nested) and _list_updatable_files(nested):
                        inner_root = nested
                        break

            for name in _list_updatable_files(inner_root):
                src = os.path.join(inner_root, name)
                dst = os.path.join(PACKAGE_DIR, name)
                shutil.copy2(src, dst)
        return True, f"已更新至 v{info.remote_version}"
    except Exception as e:
        try:
            _restore_backup(backup_dir)
        except Exception:
            pass
        return False, f"更新失败并已尝试回滚: {e}"


def apply_update(info: UpdateInfo) -> tuple:
    if not info.available:
        return True, "已是最新版本"

    if info.method == "git":
        return _apply_git_update()

    if info.method in ("github", "gitee"):
        return _apply_release_update(info)

    return False, info.detail or "未配置更新源"


def restart_script() -> None:
    os.execv(sys.executable, [sys.executable, *sys.argv])


def print_update_status(info: UpdateInfo) -> None:
    print(f"  当前版本 : v{info.local_version}")
    print(f"  最新版本 : v{info.remote_version}" if info.remote_version else "  最新版本 : 未知")
    print(f"  更新通道 : {info.method}")
    if info.detail:
        print(f"  详情     : {info.detail}")
    if info.available:
        print("  状态     : ✅ 有新版本可更新")
    elif info.remote_version == "未知" or (
        info.detail and ("error" in info.detail.lower() or "limit" in info.detail.lower() or "失败" in info.detail)
    ):
        print("  状态     : ⚠️ 版本检查失败（网络或 GitHub 限流）")
    else:
        print("  状态     : 已是最新")


def maybe_handle_update(args) -> bool:
    """处理 --update / --check-update / 启动时交互更新。返回 True 表示应退出 main。"""
    interactive = not args.daemon and not getattr(args, "check_once", False)

    if getattr(args, "check_update", False):
        info = check_for_update()
        print("\n📦 版本检查")
        print_update_status(info)
        return True

    if getattr(args, "update", False):
        info = check_for_update()
        if not info.available:
            print(f"\n✅ 已是最新版本 v{info.local_version}")
            if info.detail:
                print(f"   {info.detail}")
            return True
        print(f"\n📦 正在更新 v{info.local_version} → v{info.remote_version} …")
        ok, msg = apply_update(info)
        if ok:
            print(f"✅ {msg}，正在重启…")
            restart_script()
        print(f"❌ {msg}")
        return True

    if getattr(args, "skip_update", False):
        return False

    info = check_for_update()
    if not info.available:
        return False

    if args.daemon or getattr(args, "check_once", False):
        print(f"ℹ️  有新版本 v{info.remote_version}（当前 v{info.local_version}），可运行 --update 更新")
        return False

    if not interactive:
        return False

    print("\n" + "─" * 45)
    print(f"📦 发现新版本 v{info.remote_version}（当前 v{info.local_version}）")
    print("   更新不会覆盖 app_data/ 里的配置与密钥")
    choice = input("👉 是否立即更新并重启？[Y/n]: ").strip().lower()
    print("─" * 45 + "\n")
    if choice not in ("", "y", "yes"):
        return False

    print(f"📦 正在更新 v{info.local_version} → v{info.remote_version} …")
    ok, msg = apply_update(info)
    if ok:
        print(f"✅ {msg}，正在重启…")
        restart_script()
    print(f"❌ 更新失败: {msg}")
    print("   可稍后手动运行: python3 check_app_status.py --update\n")
    return False
