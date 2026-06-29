import os
import select
import sys
import time
from datetime import datetime

from .config import secure_dir, secure_file
from .constants import DIR_MODE_PRIVATE, FILE_MODE_PRIVATE

_countdown_active = False


def set_countdown_active(active: bool) -> None:
    global _countdown_active
    _countdown_active = active


def monitor_print(*args, **kwargs) -> None:
    """在倒计时行活跃时先清行再输出，避免终端乱码。"""
    if _countdown_active:
        sys.stdout.write("\r\033[K")
    print(*args, **kwargs)
    sys.stdout.flush()


def print_app_status_lists(config: dict) -> None:
    pending = config.get("APPS", [])
    approved = config.get("APPROVED_APPS", [])
    removed = config.get("REMOVED_APPS", [])
    print("\n📋 应用状态一览")
    print(f"  ⏳ 待监控 ({len(pending)} 个):")
    if pending:
        for i, app in enumerate(pending, 1):
            name = app.get("APP_NAME", f"App({app.get('APP_ID')})")
            print(f"     {i}. {name} (ID: {app.get('APP_ID')})")
    else:
        print("     （暂无）")
    print(f"  🟢 已过审 ({len(approved)} 个):")
    if approved:
        for i, app in enumerate(approved, 1):
            name = app.get("APP_NAME", f"App({app.get('APP_ID')})")
            ver = app.get("APPROVED_VERSION", "")
            at = app.get("APPROVED_AT", "")
            ver_str = f" v{ver}" if ver else ""
            time_str = f" · {at}" if at else ""
            print(f"     {i}. {name}{ver_str} (ID: {app.get('APP_ID')}){time_str}")
    else:
        print("     （暂无）")
    print(f"  ❌ 已下架 ({len(removed)} 个，仅记录不再监控):")
    if removed:
        for i, app in enumerate(removed, 1):
            name = app.get("APP_NAME", f"App({app.get('APP_ID')})")
            ver = app.get("REMOVED_VERSION", "")
            at = app.get("REMOVED_AT", "")
            ver_str = f" v{ver}" if ver else ""
            time_str = f" · {at}" if at else ""
            print(f"     {i}. {name}{ver_str} (ID: {app.get('APP_ID')}){time_str}")
    else:
        print("     （暂无）")


def print_unchanged_status_line(round_no: int, rows: list) -> None:
    if not rows:
        return
    try:
        cols = os.get_terminal_size().columns
    except Exception:
        cols = 100
    parts = []
    for r in rows:
        st = r["state"]
        short = st.split("(")[0].strip() if "(" in st else st
        parts.append(f"{r['name']} v{r['ver']} · {short}")
    mid = " │ ".join(parts)
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"💡 [{ts}] 第{round_no}轮 状态未变 · {mid}"
    if len(line) >= cols:
        line = line[: max(40, cols - 4)] + "…"
    sys.stdout.write("\r\033[K" + line + "\n")
    sys.stdout.flush()


def countdown_sleep(seconds, round_no: int = 0, interactive: bool = True):
    print()
    if not interactive or not sys.stdin.isatty():
        time.sleep(seconds)
        return False
    set_countdown_active(True)
    try:
        for remaining in range(seconds, 0, -1):
            tag = f"已轮询{round_no}轮 · " if round_no > 0 else ""
            sys.stdout.write(
                f"\r\033[K{tag}⏳ 距离下次查询还剩: {remaining // 60:02d}分 {remaining % 60:02d}秒 "
                f"[R 添加] [E 修改]... "
            )
            sys.stdout.flush()
            i, o, e = select.select([sys.stdin], [], [], 1)
            if i:
                user_input = sys.stdin.readline().strip().upper()
                if user_input in ("R", "E"):
                    sys.stdout.write("\r\033[K")
                    print("\n")
                    return user_input
        sys.stdout.write("\r\033[K")
        print()
        return False
    except KeyboardInterrupt:
        sys.stdout.write("\r\033[K")
        print("\n\n⏹️ 监控已手动停止。再见！")
        sys.exit(0)
    finally:
        set_countdown_active(False)


def get_user_input(prompt_text, default_value=""):
    if default_value:
        prompt = f"{prompt_text} [当前: {default_value}] (直接回车保持不变): "
    else:
        prompt = f"{prompt_text}: "
    val = input(prompt).strip()
    return val if val else default_value


def log_event(app_id, app_name, event_msg, monitor_dir=None):
    if monitor_dir and os.path.exists(monitor_dir):
        log_file = os.path.join(monitor_dir, "history.log")
        secure_dir(monitor_dir, DIR_MODE_PRIVATE)
    else:
        log_file = os.path.expanduser("~/.appstore_check_history.log")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [App: {app_name} (ID: {app_id})] {event_msg}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)
        secure_file(log_file, FILE_MODE_PRIVATE)
    except Exception:
        pass
