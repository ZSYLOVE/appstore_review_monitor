import argparse
import atexit
import os
import sys

from . import __version__
from .auth import clear_secret_caches
from .config import load_config, merge_apps_from_json, normalize_json_path, save_config
from .constants import CONFIG_FILE, DEFAULT_PROXY_PORT
from .fingerprint import generate_run_fingerprint
from .monitor import run_monitor_loop
from .security import print_security_status
from .session import configure_session, validate_apple_connectivity
from .update import maybe_handle_update

atexit.register(clear_secret_caches)


def parse_cli_args():
    parser = argparse.ArgumentParser(
        description="App Store Connect 审核状态自动监控与通知助手",
    )
    parser.add_argument(
        "--config",
        default=None,
        help=f"配置文件路径（默认: {CONFIG_FILE}）",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="非交互模式，直接使用缓存配置运行（适合 launchd/cron）",
    )
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="只执行一轮巡检后退出",
    )
    parser.add_argument(
        "--no-security-panel",
        action="store_true",
        help="启动时不显示防护状态面板（默认显示）",
    )
    parser.add_argument(
        "--import-json",
        default=None,
        help="启动时从指定 JSON 文件合并应用配置",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="代理地址，如 http://127.0.0.1:7897；传 0 表示不使用代理",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="检查并安装最新版本，完成后自动重启",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="仅检查是否有新版本",
    )
    parser.add_argument(
        "--skip-update",
        action="store_true",
        help="跳过启动时的版本检查",
    )
    return parser.parse_args()


def resolve_proxy(config: dict, proxy_arg: str = None, *, interactive: bool = True) -> str:
    saved_proxy = config.get("PROXY", f"http://127.0.0.1:{DEFAULT_PROXY_PORT}")

    if proxy_arg is not None:
        if proxy_arg == "0":
            return ""
        if proxy_arg.isdigit():
            return f"http://127.0.0.1:{proxy_arg}"
        return proxy_arg

    if not interactive:
        return saved_proxy

    print("\n" + "─" * 45)
    print("🌐 代理设置（用于访问苹果 API）")
    print("─" * 45)
    print(f"   默认: http://127.0.0.1:{DEFAULT_PROXY_PORT}（Clash/V2Ray 常用端口）")
    print(f"   当前缓存: {saved_proxy or '不使用代理'}")
    print("   支持格式: http://127.0.0.1:端口  或  socks5://127.0.0.1:端口")
    print("   直接回车 = 沿用当前缓存；输入 0 = 不使用代理")
    strict = config.get("STRICT_PROXY", False)
    if strict:
        print("   ⚠️  STRICT_PROXY 已启用：必须配置代理，禁止直连 Apple API")
    proxy_input = input("👉 请输入代理地址（或端口号，如 7897）: ").strip()

    if proxy_input == "0":
        if strict:
            print("   ❌ STRICT_PROXY 模式下不能选择不使用代理。")
            return resolve_proxy(config, proxy_arg=None, interactive=True)
        current_proxy = ""
        print("   ✅ 已设置为不使用代理。")
    elif proxy_input == "":
        current_proxy = saved_proxy
        print(f"   ✅ 沿用缓存代理: {current_proxy or '不使用代理'}")
    elif proxy_input.isdigit():
        current_proxy = f"http://127.0.0.1:{proxy_input}"
        print(f"   ✅ 已设置代理: {current_proxy}")
    else:
        current_proxy = proxy_input
        print(f"   ✅ 已设置代理: {current_proxy}")
    print("─" * 45 + "\n")
    return current_proxy


def main():
    args = parse_cli_args()
    if maybe_handle_update(args):
        return

    config_path = os.path.expanduser(args.config) if args.config else CONFIG_FILE
    interactive = not args.daemon and not args.check_once

    print("=========================================")
    print("🚀 App Store 自动化审核监控与通知助手 (多应用版)")
    print("=========================================")
    print(f"   版本 v{__version__}\n")

    config = load_config(config_path)
    apps = config.get("APPS", [])

    if args.import_json:
        import_path = normalize_json_path(args.import_json)
        if os.path.exists(import_path):
            try:
                added = merge_apps_from_json(import_path, apps, config)
                config["APPS"] = apps
                if added:
                    save_config(config, config_path, refresh_names=True)
                print(f"✅ 从 {import_path} 合并了 {added} 个应用")
            except Exception as e:
                print(f"❌ 导入配置失败: {e}")
                sys.exit(1)
        else:
            print(f"❌ 找不到配置文件: {import_path}")
            sys.exit(1)

    if interactive:
        print("👉 [配置加载] 如果您有之前保存的 .json 配置文件，请直接【拖拽】到终端并按回车。")
        print("👉 [配置加载] 如果没有，或者想使用之前成功的缓存，请直接按【回车键】。")
        print("👉 [配置加载] 如果想清空配置并重新录入，请输入【R】并按回车：")
        drag_input = normalize_json_path(input("> ").strip())

        if drag_input.upper() == "R":
            print("\n🔄 进入重新录入模式。")
            config = {
                "APPS": [],
                "APPROVED_APPS": config.get("APPROVED_APPS", []),
                "REMOVED_APPS": config.get("REMOVED_APPS", []),
                "PROXY": config.get("PROXY", f"http://127.0.0.1:{DEFAULT_PROXY_PORT}"),
                "DEFAULT_PUSHPLUS": config.get("DEFAULT_PUSHPLUS", ""),
                "DEFAULT_FEISHU": config.get("DEFAULT_FEISHU", ""),
                "AUTO_REMOVE_ON_APPROVE": config.get("AUTO_REMOVE_ON_APPROVE", False),
                "STRICT_PROXY": config.get("STRICT_PROXY", False),
            }
            apps = []
        elif drag_input and os.path.exists(drag_input) and drag_input.endswith(".json"):
            try:
                added = merge_apps_from_json(drag_input, apps, config)
                config["APPS"] = apps
                if added:
                    save_config(config, config_path, refresh_names=True)
                print(f"✅ 成功加载外部配置文件: {drag_input}")
            except Exception as e:
                print(f"❌ 解析拖拽的配置文件失败: {e}")
    elif not apps:
        print("⚠️ daemon 模式需要已有配置，请先交互式运行一次或提供 --import-json。")
        print(f"   配置文件: {config_path}")
        sys.exit(1)

    run_fp = generate_run_fingerprint()
    current_proxy = resolve_proxy(config, args.proxy, interactive=interactive)
    config["PROXY"] = current_proxy
    if not save_config(config, config_path, sync_dirs=False):
        print("   ⚠️  代理配置未能写入磁盘，本次仍按内存中的设置运行。")

    configure_session(
        proxy_url=current_proxy,
        impersonate=run_fp["impersonate"],
        strict_proxy=bool(config.get("STRICT_PROXY")),
        base_headers=run_fp["headers"],
    )

    if current_proxy:
        print(f"   🔗 Apple Session 已绑定代理 {current_proxy}")
    else:
        print("   🔗 Apple Session 已初始化（直连，不走代理）")
        if config.get("STRICT_PROXY"):
            print("   ❌ STRICT_PROXY 已启用但未配置代理。")
            sys.exit(1)

    if current_proxy or config.get("STRICT_PROXY"):
        ok, detail = validate_apple_connectivity()
        if ok:
            print(f"   ✅ Apple API 连通正常（{detail}）")
        else:
            print(f"   ❌ 无法连通 Apple API: {detail}")
            print(f"   💡 请确认 Clash 已运行，且 fake-ip-filter 含 apple.com、规则走代理")
            if config.get("STRICT_PROXY"):
                sys.exit(1)
            print("   ⚠️  将继续运行，但请求可能失败。")

    print(f"   🔒 第三方通知使用独立 Session（与 Apple API 隔离）")
    print(f"   🎭 TLS/UA 指纹: {run_fp['impersonate']} / Chrome {run_fp['chrome_version']}（本次运行随机）")

    if not args.no_security_panel:
        print_security_status(current_proxy)

    run_monitor_loop(
        config,
        apps,
        config_path=config_path,
        check_once=args.check_once,
        interactive=interactive,
    )
