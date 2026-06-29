import json
import os
import random
import shutil
from datetime import datetime
from typing import List

from .api import fetch_app_name_sync
from .constants import (
    APP_DATA_DIR,
    CHECK_INTERVAL_RANDOM_MAX,
    CHECK_INTERVAL_RANDOM_MIN,
    CONFIG_FILE,
    DEFAULT_PROXY_PORT,
    DEFAULT_UPDATE_REPO,
    DIR_MODE_PRIVATE,
    FILE_MODE_PRIVATE,
)


def format_interval_minutes(seconds: int) -> str:
    if seconds % 60 == 0:
        return str(seconds // 60)
    return f"{seconds / 60:.1f}"


def random_check_interval() -> int:
    """新应用默认轮询间隔（秒），多人使用时错开请求节奏。"""
    return random.randint(CHECK_INTERVAL_RANDOM_MIN, CHECK_INTERVAL_RANDOM_MAX)


def secure_file(path: str, mode: int = FILE_MODE_PRIVATE) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def secure_dir(path: str, mode: int = DIR_MODE_PRIVATE) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def apply_config_defaults(config: dict) -> dict:
    if not isinstance(config, dict):
        return {
            "APPS": [],
            "APPROVED_APPS": [],
            "REMOVED_APPS": [],
            "AUTO_REMOVE_ON_APPROVE": False,
            "STRICT_PROXY": False,
            "UPDATE_REPO": DEFAULT_UPDATE_REPO,
        }
    if "AUTO_REMOVE_ON_APPROVE" not in config:
        config["AUTO_REMOVE_ON_APPROVE"] = False
    if "APPROVED_APPS" not in config or not isinstance(config.get("APPROVED_APPS"), list):
        config["APPROVED_APPS"] = []
    if "REMOVED_APPS" not in config or not isinstance(config.get("REMOVED_APPS"), list):
        config["REMOVED_APPS"] = []
    if "APPS" not in config or not isinstance(config.get("APPS"), list):
        config["APPS"] = []
    env_strict = os.environ.get("APPSTORE_CHECK_STRICT_PROXY", "").strip().lower()
    if "STRICT_PROXY" not in config:
        config["STRICT_PROXY"] = env_strict in ("1", "true", "yes", "on")
    if "COMPACT_OUTPUT" not in config:
        config["COMPACT_OUTPUT"] = False
    if "UPDATE_REPO" not in config or not str(config.get("UPDATE_REPO", "")).strip():
        env_repo = os.environ.get("APPSTORE_MONITOR_UPDATE_REPO", "").strip()
        config["UPDATE_REPO"] = env_repo or DEFAULT_UPDATE_REPO
    return config


def normalize_json_path(path: str) -> str:
    return path.strip("'").strip('"').replace("\\ ", " ")


def is_placeholder_app_name(name: str, app_id: str) -> bool:
    if not name or name == "未知":
        return True
    return name == f"App({app_id})"


def parse_apps_from_json_file(json_path: str) -> list:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    apps = []
    if isinstance(data, dict):
        if "APPS" in data:
            apps = list(data["APPS"])
        elif "APP_ID" in data:
            apps = [data]
    for app in apps:
        if "CHECK_INTERVAL" not in app:
            app["CHECK_INTERVAL"] = random_check_interval()
        app.setdefault("REVIEW_INTERVAL", 180)
    return apps


def app_config_lists(config: dict, app_id: str) -> List[str]:
    """返回 app_id 所在列表名：APPS / APPROVED_APPS / REMOVED_APPS。"""
    found = []
    if any(a.get("APP_ID") == app_id for a in config.get("APPS", [])):
        found.append("APPS")
    if any(a.get("APP_ID") == app_id for a in config.get("APPROVED_APPS", [])):
        found.append("APPROVED_APPS")
    if any(a.get("APP_ID") == app_id for a in config.get("REMOVED_APPS", [])):
        found.append("REMOVED_APPS")
    return found


def merge_apps_from_json(json_path: str, apps: list, config: dict = None) -> int:
    try:
        apps_to_add = parse_apps_from_json_file(json_path)
    except Exception as e:
        raise ValueError(str(e)) from e

    added_count = 0
    existing_ids = {a.get("APP_ID") for a in apps}
    removed_ids = set()
    approved_ids = set()
    if config:
        removed_ids = {a.get("APP_ID") for a in config.get("REMOVED_APPS", [])}
        approved_ids = {a.get("APP_ID") for a in config.get("APPROVED_APPS", [])}
    base_dir = os.path.dirname(json_path)
    for new_app in apps_to_add:
        app_id = new_app.get("APP_ID")
        if not app_id or app_id in existing_ids:
            continue
        if app_id in removed_ids:
            print(f"⚠️ 应用 {app_id} 已在「已下架」列表，跳过（下架为终态，不会重新监控）。")
            continue
        if app_id in approved_ids:
            print(f"⚠️ 应用 {app_id} 已在「已过审」列表并持续监控，跳过重复添加。")
            continue
        saved_p8 = new_app.get("P8_PATH", "")
        if saved_p8 and not os.path.exists(saved_p8):
            possible_p8 = os.path.join(base_dir, os.path.basename(saved_p8))
            if os.path.exists(possible_p8):
                new_app["P8_PATH"] = possible_p8
                print(f"🔄 自动修正应用 {app_id} 的密钥路径为: {possible_p8}")
        apps.append(new_app)
        existing_ids.add(app_id)
        added_count += 1
    return added_count


def archive_approved_app(config: dict, app: dict, version_string: str, app_store_state: str) -> None:
    archived = dict(app)
    archived["APPROVED_AT"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archived["APPROVED_VERSION"] = version_string
    archived["APPROVED_STATE"] = app_store_state
    approved = [a for a in config.get("APPROVED_APPS", []) if a.get("APP_ID") != app.get("APP_ID")]
    approved.append(archived)
    config["APPROVED_APPS"] = approved
    config["APPS"] = [a for a in config.get("APPS", []) if a.get("APP_ID") != app.get("APP_ID")]


def archive_removed_app(config: dict, app: dict, version_string: str, app_store_state: str) -> None:
    """归档至已下架列表。终态：不再轮询、不会重新上架监控。"""
    archived = dict(app)
    archived["REMOVED_AT"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archived["REMOVED_VERSION"] = version_string
    archived["REMOVED_STATE"] = app_store_state
    removed = [a for a in config.get("REMOVED_APPS", []) if a.get("APP_ID") != app.get("APP_ID")]
    removed.append(archived)
    config["REMOVED_APPS"] = removed
    config["APPROVED_APPS"] = [
        a for a in config.get("APPROVED_APPS", []) if a.get("APP_ID") != app.get("APP_ID")
    ]


def restore_app_to_pending(config: dict, app: dict) -> None:
    """已过审应用出现新版本或非上架态时，移回待监控列表（不含已下架终态）。"""
    app_id = app.get("APP_ID")
    restored = dict(app)
    for key in ("APPROVED_AT", "APPROVED_VERSION", "APPROVED_STATE"):
        restored.pop(key, None)
    config["APPROVED_APPS"] = [
        a for a in config.get("APPROVED_APPS", []) if a.get("APP_ID") != app_id
    ]
    if not any(a.get("APP_ID") == app_id for a in config.get("APPS", [])):
        config.setdefault("APPS", []).append(restored)


LEGACY_CONFIG_FILE = os.path.expanduser("~/.appstore_check_config.json")


def _print_save_permission_hint(path: str, err: Exception) -> None:
    print(f"\n⚠️  配置保存失败: {err}")
    print(f"   目标: {path}")
    print("   常见原因:")
    print("   • 项目在「下载」目录，macOS 可能限制终端写入 → 建议移到 ~/Documents")
    print("   • 系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 允许终端/iTerm")
    print("   • 检查文件是否被锁定: chflags nouchg <路径>")


def _write_json_atomic(path: str, data) -> None:
    dir_name = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dir_name, exist_ok=True)
    tmp_path = os.path.join(dir_name, f".{os.path.basename(path)}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    secure_file(path)


def load_config(config_path: str = None) -> dict:
    path = config_path or CONFIG_FILE
    if path == CONFIG_FILE and not os.path.exists(path) and os.path.exists(LEGACY_CONFIG_FILE):
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        secure_dir(APP_DATA_DIR)
        shutil.copy2(LEGACY_CONFIG_FILE, path)
        secure_file(path)
        print(f"📦 已从旧位置迁移主配置到: {path}")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "APPS" in data:
                        return apply_config_defaults(data)
                    if "APP_ID" in data:
                        return apply_config_defaults({"APPS": [data]})
                    return apply_config_defaults({"APPS": []})
                return apply_config_defaults({"APPS": []})
        except Exception:
            pass
    return apply_config_defaults(
        {
            "APPS": [],
            "PROXY": f"http://127.0.0.1:{DEFAULT_PROXY_PORT}",
            "DEFAULT_PUSHPLUS": "",
            "DEFAULT_FEISHU": "",
        }
    )


def _app_monitor_dir(app_name: str, app_id: str) -> str:
    safe_app_name = "".join([c for c in app_name if c.isalnum() or c in (" ", "-", "_")]).strip()
    folder = f"AppStoreMonitor_{safe_app_name}_{app_id}" if safe_app_name else f"AppStoreMonitor_{app_id}"
    return os.path.join(APP_DATA_DIR, folder)


def _resolve_p8_path(app: dict) -> str:
    p8_path = app.get("P8_PATH", "")
    if p8_path and os.path.exists(p8_path):
        return p8_path
    monitor_dir = app.get("MONITOR_DIR")
    if monitor_dir:
        candidate = os.path.join(monitor_dir, os.path.basename(p8_path or ""))
        if os.path.exists(candidate):
            return candidate
    return p8_path


def _sync_app_monitor_dir(app: dict) -> None:
    app_id = app.get("APP_ID", "")
    if not app_id:
        return

    p8_path = _resolve_p8_path(app)
    if not p8_path or not os.path.exists(p8_path):
        return

    app_name = app.get("APP_NAME", f"App({app_id})")
    monitor_dir = _app_monitor_dir(app_name, app_id)
    legacy_dir = app.get("MONITOR_DIR")

    os.makedirs(monitor_dir, exist_ok=True)
    secure_dir(monitor_dir)

    dest_p8 = os.path.join(monitor_dir, os.path.basename(p8_path))
    if os.path.abspath(p8_path) != os.path.abspath(dest_p8):
        shutil.copy2(p8_path, dest_p8)
    app["P8_PATH"] = dest_p8
    secure_file(dest_p8)

    if legacy_dir and os.path.abspath(legacy_dir) != os.path.abspath(monitor_dir):
        legacy_log = os.path.join(legacy_dir, "history.log")
        new_log = os.path.join(monitor_dir, "history.log")
        if os.path.exists(legacy_log) and not os.path.exists(new_log):
            shutil.copy2(legacy_log, new_log)
            secure_file(new_log)

    export_file = os.path.join(monitor_dir, "config.json")
    try:
        _write_json_atomic(export_file, app)
    except PermissionError:
        pass

    app["MONITOR_DIR"] = monitor_dir


def _sync_monitor_dirs(config: dict, *, refresh_names: bool = False) -> None:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    secure_dir(APP_DATA_DIR)
    for list_key in ("APPS", "APPROVED_APPS", "REMOVED_APPS"):
        for app in config.get(list_key, []):
            app_id = app.get("APP_ID", "")
            if refresh_names or is_placeholder_app_name(app.get("APP_NAME", ""), app_id):
                fetch_app_name_sync(app)
            _sync_app_monitor_dir(app)


def save_config(
    config,
    config_path: str = None,
    *,
    sync_dirs: bool = True,
    refresh_names: bool = False,
) -> bool:
    """保存配置；成功返回 True。权限失败时尝试 ~/.appstore_check_config.json。"""
    apply_config_defaults(config)
    path = config_path or CONFIG_FILE
    if sync_dirs:
        _sync_monitor_dirs(config, refresh_names=refresh_names)

    try:
        _write_json_atomic(path, config)
        return True
    except PermissionError as err:
        fallback = LEGACY_CONFIG_FILE
        if os.path.abspath(path) != os.path.abspath(fallback):
            try:
                _write_json_atomic(fallback, config)
                print(f"⚠️  无法写入 {path}，已改存 {fallback}")
                return True
            except PermissionError:
                pass
        _print_save_permission_hint(path, err)
        return False
