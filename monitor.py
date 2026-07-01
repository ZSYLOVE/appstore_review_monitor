import atexit
import fcntl
import os
import signal
import sys
from datetime import datetime

import psutil

from .api import apple_error_detail
from .auth import get_token_for_app
from .config import (
    archive_approved_app,
    archive_removed_app,
    is_placeholder_app_name,
    restore_app_to_pending,
    save_config,
)
from .constants import (
    APP_DATA_DIR,
    APP_STORE_STATES,
    APPROVED_STATES,
    CONFIG_FILE,
    DELISTED_STATES,
    REJECTED_STATES,
)
from .notify import (
    notify_delisted,
    notify_rejected,
    notify_status_change,
    notify_success,
    notify_version_change,
)
from .session import apple_headers, get_with_backoff, jitter, sleep_backoff
from .setup_apps import interactive_add_apps, interactive_edit_apps
from .ui import countdown_sleep, log_event, print_app_status_lists, print_unchanged_status_line


MONITOR_LOCK_FILE = os.path.join(APP_DATA_DIR, ".monitor.lock")

_lock_handle = None
_lock_path = None
_lock_handlers_registered = False


def _lock_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_lock_pid(lock_path: str):
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def release_monitor_lock() -> None:
    global _lock_handle, _lock_path
    if _lock_handle is not None:
        try:
            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            _lock_handle.close()
        except OSError:
            pass
        _lock_handle = None
    if _lock_path and os.path.exists(_lock_path):
        try:
            os.remove(_lock_path)
        except OSError:
            pass


def _exit_with_lock_release(message: str = "", code: int = 0) -> None:
    if message:
        print(message)
    release_monitor_lock()
    sys.exit(code)


def _register_lock_handlers() -> None:
    global _lock_handlers_registered
    if _lock_handlers_registered:
        return
    _lock_handlers_registered = True
    atexit.register(release_monitor_lock)

    def _on_interrupt(signum, frame):
        sig_name = "Ctrl+C" if signum == signal.SIGINT else "停止信号"
        _exit_with_lock_release(f"\n\n⏹️ 监控已停止（{sig_name}，已释放锁文件）。", 0)

    def _on_sigtstp(signum, frame):
        _exit_with_lock_release(
            "\n\n⏹️ 监控已停止（Ctrl+Z，已释放锁文件）。下次可直接重新启动。",
            0,
        )

    signal.signal(signal.SIGINT, _on_interrupt)
    signal.signal(signal.SIGTERM, _on_interrupt)
    signal.signal(signal.SIGTSTP, _on_sigtstp)


def _acquire_single_instance_lock(config_path: str = None):
    global _lock_handle, _lock_path
    lock_path = MONITOR_LOCK_FILE
    if config_path and os.path.abspath(config_path) != os.path.abspath(CONFIG_FILE):
        lock_path = os.path.join(
            os.path.dirname(os.path.abspath(config_path)), ".appstore_check_monitor.lock"
        )
    _lock_path = lock_path
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    stale_pid = _read_lock_pid(lock_path)
    if stale_pid is not None and not _lock_pid_alive(stale_pid):
        try:
            os.remove(lock_path)
        except OSError:
            pass

    lock_handle = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        holder_pid = _read_lock_pid(lock_path)
        print("❌ 已有监控进程在运行，请勿重复启动（会导致重复推送与终端输出错乱）。")
        if holder_pid and _lock_pid_alive(holder_pid):
            print(f"   占用进程 PID: {holder_pid}")
            try:
                if psutil.Process(holder_pid).status() == psutil.STATUS_STOPPED:
                    print("   该进程处于挂起状态（可能由 Ctrl+Z 导致）。")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            print(f"   可执行: kill {holder_pid}")
        print(f"   或手动删除锁文件: {lock_path}")
        print("   💡 提示: Ctrl+Z 会先释放锁再退出；Ctrl+C 同样会释放锁。")
        sys.exit(1)

    lock_handle.write(str(os.getpid()))
    lock_handle.flush()
    _lock_handle = lock_handle
    _register_lock_handlers()
    return lock_handle


def _collect_monitor_targets(config, app_states):
    targets = []
    for app in config.get("APPS", []):
        app_id = app["APP_ID"]
        if app_states.get(app_id, {}).get("is_done"):
            continue
        targets.append((app, "APPS"))
    for app in config.get("APPROVED_APPS", []):
        targets.append((app, "APPROVED_APPS"))
    return targets


def _ensure_app_state(app_id, app, source, app_states):
    if app_id in app_states:
        return app_states[app_id]
    initial_state = None
    initial_version = None
    if source == "APPROVED_APPS":
        initial_state = app.get("APPROVED_STATE")
        initial_version = app.get("APPROVED_VERSION")
    else:
        initial_state = app.get("LAST_STORE_STATE")
        initial_version = app.get("LAST_VERSION_STRING")
    app_states[app_id] = {
        "last_state": initial_state,
        "last_version": initial_version,
        "next_sleep_time": 600,
        "is_done": False,
        "source": source,
    }
    return app_states[app_id]


def run_monitor_loop(
    config,
    apps,
    *,
    config_path: str = None,
    check_once: bool = False,
    interactive: bool = True,
):
    auto_remove = bool(config.get("AUTO_REMOVE_ON_APPROVE", False))
    _lock_handle = _acquire_single_instance_lock(config_path or CONFIG_FILE)
    pending_interactive = "add" if interactive else None

    while True:
        if interactive and pending_interactive == "add":
            interactive_add_apps(config, apps, config_path)
        elif interactive and pending_interactive == "edit":
            interactive_edit_apps(config, apps, config_path)
        pending_interactive = None

        if not config.get("APPS") and not config.get("APPROVED_APPS"):
            print("⚠️ 未配置任何需要监控的应用，脚本退出。")
            sys.exit(0)

        print("\n✅ 配置读取完毕，开始进入多应用 24 小时监控模式...")
        if interactive:
            print("💡 倒计时期间按 R+回车 添加应用，E+回车 修改应用配置。")
        if config.get("APPROVED_APPS"):
            print("💡 已过审应用已从待监控列表移出，后台静默监控（下架或新版本时才会通知）。")

        app_states = {}

        interrupted = False
        round_no = 0
        config_dirty = False
        compact = bool(config.get("COMPACT_OUTPUT", False))

        while True:
            round_no += 1
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            round_banner_printed = False
            unchanged_rows: list = []

            def ensure_round_banner() -> None:
                nonlocal round_banner_printed
                if round_banner_printed:
                    return
                round_banner_printed = True
                try:
                    process = psutil.Process()
                    mem_mb = process.memory_info().rss / 1024 / 1024
                    mem_info = f" | 💻 内存: {mem_mb:.1f} MB"
                except Exception:
                    mem_info = ""
                print("\n=========================================")
                print(f"🔄 [{current_time}] 开始第 {round_no} 轮巡检...{mem_info}")
                print("=========================================")

            monitor_targets = _collect_monitor_targets(config, app_states)
            has_pending = any(source == "APPS" for _, source in monitor_targets)

            if not compact and has_pending:
                ensure_round_banner()

            if not monitor_targets:
                print("\n🎉 所有监控任务已完成！")
                print_app_status_lists(config)
                if config_dirty:
                    if save_config(config, config_path, sync_dirs=False):
                        config_dirty = False
                return

            for app, source in monitor_targets:
                app_id = app["APP_ID"]
                state = _ensure_app_state(app_id, app, source, app_states)
                pushplus_token = app.get("PUSHPLUS_TOKEN") or config.get("DEFAULT_PUSHPLUS", "")
                feishu_webhook = app.get("FEISHU_WEBHOOK") or config.get("DEFAULT_FEISHU", "")
                app_name = app.get("APP_NAME", f"App({app_id})")
                header_printed = False
                need_app_name = is_placeholder_app_name(app_name, app_id)
                list_tag = "已过审" if source == "APPROVED_APPS" else "待监控"

                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        token = get_token_for_app(app)
                    except Exception as e:
                        ensure_round_banner()
                        print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                        print(f"  ❌ 生成 Token 失败，跳过该应用。请检查 P8 密钥: {e}")
                        print("  💡 倒计时期间按 E+回车 可修改该应用配置。")
                        break

                    h = apple_headers(token)

                    try:
                        jitter()

                        if need_app_name:
                            res_info = get_with_backoff(
                                f"https://api.appstoreconnect.apple.com/v1/apps/{app_id}",
                                h,
                            )
                            if res_info.status_code == 200:
                                fetched_name = res_info.json().get("data", {}).get("attributes", {}).get("name")
                                if fetched_name and fetched_name != app_name:
                                    app["APP_NAME"] = fetched_name
                                    app_name = fetched_name
                                    need_app_name = False
                                    config_dirty = True
                            else:
                                detail = apple_error_detail(res_info)
                                ensure_round_banner()
                                print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                                print(f"  ❌ 查询应用信息失败 ({res_info.status_code}) {detail}")
                                if res_info.status_code in (401, 403):
                                    print("  💡 认证信息可能有误，倒计时期间按 E+回车 可修改该应用配置。")
                                log_event(
                                    app_id,
                                    app_name,
                                    f"查询应用失败: HTTP {res_info.status_code} {detail}",
                                    app.get("MONITOR_DIR"),
                                )
                                break
                            jitter(400)

                        url = f"https://api.appstoreconnect.apple.com/v1/apps/{app_id}/appStoreVersions?limit=10"
                        response = get_with_backoff(url, h)
                        if response.status_code != 200:
                            detail = apple_error_detail(response)
                            ensure_round_banner()
                            print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                            print(f"  ❌ 查询版本状态失败 ({response.status_code}) {detail}")
                            if response.status_code in (400, 401, 403, 404):
                                print("  🚨 认证失败或 App 未找到，请稍后检查该 App 的配置。")
                                if response.status_code in (401, 403):
                                    print("  💡 倒计时期间按 E+回车 可修改该应用配置。")
                            log_event(
                                app_id,
                                app_name,
                                f"查询版本失败: HTTP {response.status_code} {detail}",
                                app.get("MONITOR_DIR"),
                            )
                            break

                        data = response.json()
                        versions = data.get("data", [])
                        if not versions:
                            msg = "⚠️ 未找到任何发布版本信息。"
                            ensure_round_banner()
                            print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                            print(f"  {msg}")
                            log_event(app_id, app_name, msg, app.get("MONITOR_DIR"))
                            break

                        latest_version = versions[0]
                        attributes = latest_version.get("attributes", {})
                        version_string = attributes.get("versionString", "未知版本")
                        app_store_state = attributes.get("appStoreState", "UNKNOWN_STATE")
                        friendly_state = APP_STORE_STATES.get(
                            app_store_state, f"❓ 未知状态 ({app_store_state})"
                        )

                        last_state = state["last_state"]
                        last_version = state["last_version"]
                        state_changed = last_state is not None and last_state != app_store_state
                        version_changed = last_version is not None and last_version != version_string
                        # 已过审且仍在上架、无变化 → 静默轮询，不刷屏
                        silent_approved = (
                            source == "APPROVED_APPS"
                            and last_state is not None
                            and not state_changed
                            and not version_changed
                            and app_store_state in APPROVED_STATES
                        )
                        should_emit = (
                            not silent_approved
                            and (
                                (not compact)
                                or (last_state is None)
                                or state_changed
                                or version_changed
                            )
                        )

                        if should_emit:
                            ensure_round_banner()
                            if not header_printed:
                                print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                                header_printed = True
                            print(f"  📱 版本: {version_string}")
                            print(f"  📌 状态: {friendly_state}")
                        elif compact:
                            unchanged_rows.append(
                                {"name": app_name, "ver": version_string, "state": friendly_state}
                            )

                        if not silent_approved and (
                            last_state is None or state_changed or version_changed
                        ):
                            log_event(
                                app_id,
                                app_name,
                                f"查询成功: v{version_string} · {friendly_state}",
                                app.get("MONITOR_DIR"),
                            )

                        if version_changed:
                            msg = f"🔔 版本发生变化: v{last_version} -> v{version_string}"
                            ensure_round_banner()
                            if not header_printed:
                                print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                                header_printed = True
                            print(f"  {msg}")
                            log_event(app_id, app_name, msg, app.get("MONITOR_DIR"))
                            notify_version_change(
                                app_id,
                                app_name,
                                last_version,
                                version_string,
                                friendly_state,
                                pushplus_token,
                                feishu_webhook,
                            )

                        if state_changed:
                            old_friendly_state = APP_STORE_STATES.get(
                                last_state, f"❓ 未知状态 ({last_state})"
                            )
                            msg = f"🔔 状态发生变化: 从 [{old_friendly_state}] -> [{friendly_state}]"
                            ensure_round_banner()
                            if not header_printed:
                                print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                                header_printed = True
                            print(f"  {msg}")
                            log_event(app_id, app_name, msg, app.get("MONITOR_DIR"))
                            if app_store_state in DELISTED_STATES:
                                notify_delisted(
                                    app_id, app_name, version_string, pushplus_token, feishu_webhook
                                )
                            elif app_store_state in APPROVED_STATES:
                                pass  # 过审专用通知见下方 notify_success，避免重复推送
                            elif app_store_state in REJECTED_STATES and last_state not in REJECTED_STATES:
                                notify_rejected(app_id, app_name, pushplus_token, feishu_webhook)
                            else:
                                notify_status_change(
                                    app_id,
                                    app_name,
                                    old_friendly_state,
                                    friendly_state,
                                    pushplus_token,
                                    feishu_webhook,
                                )

                        state["last_state"] = app_store_state
                        state["last_version"] = version_string
                        if (
                            app.get("LAST_STORE_STATE") != app_store_state
                            or app.get("LAST_VERSION_STRING") != version_string
                        ):
                            app["LAST_STORE_STATE"] = app_store_state
                            app["LAST_VERSION_STRING"] = version_string
                            config_dirty = True

                        if app_store_state == "IN_REVIEW":
                            state["next_sleep_time"] = int(app.get("REVIEW_INTERVAL", 180))
                        else:
                            state["next_sleep_time"] = int(app.get("CHECK_INTERVAL", 600))

                        if source == "APPROVED_APPS":
                            if app_store_state in DELISTED_STATES:
                                if should_emit or state_changed:
                                    ensure_round_banner()
                                    print("  ❌ 应用已下架，移入「已下架」列表并停止监控。")
                                log_event(
                                    app_id,
                                    app_name,
                                    f"❌ 已下架: v{version_string} · {friendly_state}",
                                    app.get("MONITOR_DIR"),
                                )
                                archive_removed_app(config, app, version_string, app_store_state)
                                app_states.pop(app_id, None)
                                config_dirty = True
                            elif app_store_state not in APPROVED_STATES or version_changed:
                                if should_emit or state_changed or version_changed:
                                    ensure_round_banner()
                                    print("  ♻️ 检测到新版本或非上架状态，移回「待监控」列表。")
                                restore_app_to_pending(config, app)
                                state["is_done"] = False
                                state["source"] = "APPS"
                                apps[:] = config.get("APPS", [])
                                config_dirty = True
                        elif app_store_state in APPROVED_STATES:
                            if should_emit:
                                ensure_round_banner()
                                print("  🎉🎉🎉 太棒了！审核通过！")
                                if auto_remove:
                                    print("  ✨ 已从监控列表移除（AUTO_REMOVE_ON_APPROVE=true）。")
                                else:
                                    print("  ✨ 已移入「已过审」列表，继续监控下架与新版本。")
                            log_event(
                                app_id,
                                app_name,
                                "✅ 审核通过！" + ("已删除。" if auto_remove else "已归档至已过审列表。"),
                                app.get("MONITOR_DIR"),
                            )
                            if state_changed:
                                notify_success(app_id, app_name, pushplus_token, feishu_webhook)
                            state["is_done"] = True
                            if auto_remove:
                                config["APPS"] = [
                                    a for a in config.get("APPS", []) if a.get("APP_ID") != app_id
                                ]
                            else:
                                archive_approved_app(config, app, version_string, app_store_state)
                                state["source"] = "APPROVED_APPS"
                                state["is_done"] = False
                            apps[:] = config.get("APPS", [])
                            config_dirty = True
                        elif app_store_state in REJECTED_STATES:
                            if should_emit and not state_changed:
                                ensure_round_banner()
                                if not header_printed:
                                    print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                                    header_printed = True
                                print("  🔴 依然是被拒绝状态。")

                        break

                    except Exception as e:
                        ensure_round_banner()
                        print(f"\n🔍 [第{round_no}轮·{list_tag}] 正在检查 {app_name} (ID: {app_id})...")
                        status_code = getattr(getattr(e, "response", None), "status_code", None)
                        if status_code:
                            resp = getattr(e, "response", None)
                            detail = apple_error_detail(resp) if resp is not None else ""
                            print(f"  ❌ 请求苹果接口失败 (状态码: {status_code}) {detail}")
                            if status_code in [400, 401, 403, 404]:
                                print("  🚨 认证失败或 App 未找到，请稍后检查该 App 的配置。")
                                if status_code in (401, 403):
                                    print("  💡 倒计时期间按 E+回车 可修改该应用配置。")
                            break
                        print(f"  ❌ 网络异常: {e}")
                        if attempt < max_retries - 1:
                            print(f"  ⏳ 退避重试 ({attempt + 1}/{max_retries})...")
                            sleep_backoff(attempt)
                        else:
                            print("  ⚠️ 多次重试均失败，跳过本轮该应用。")

                if interrupted:
                    break

            if interrupted:
                break

            if config_dirty:
                if save_config(config, config_path, sync_dirs=False):
                    config_dirty = False
                else:
                    print("  ⚠️  本轮配置未写入磁盘，下轮将继续重试保存。")

            if compact and not round_banner_printed and unchanged_rows:
                print_unchanged_status_line(round_no, unchanged_rows)

            monitor_targets = _collect_monitor_targets(config, app_states)
            if not monitor_targets:
                break

            if check_once:
                print("\n✅ --check-once 模式：本轮巡检完成，退出。")
                print_app_status_lists(config)
                return

            min_sleep = min(app_states[t[0]["APP_ID"]]["next_sleep_time"] for t in monitor_targets)

            if round_banner_printed or (not compact and has_pending):
                print("\n" + "-" * 40)
                print(f"📋 第 {round_no} 轮巡检完毕")
                print_app_status_lists(config)

            cmd = countdown_sleep(min_sleep, round_no=round_no, interactive=interactive)
            if cmd == "R":
                print("\n🔄 [用户打断] 您按下了 R 键。即将进入添加应用模式...")
                pending_interactive = "add"
                interrupted = True
                break
            if cmd == "E":
                print("\n🔄 [用户打断] 您按下了 E 键。即将进入修改应用配置模式...")
                pending_interactive = "edit"
                interrupted = True
                break

        if not interrupted:
            break
