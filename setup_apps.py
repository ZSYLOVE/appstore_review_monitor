import os
from typing import Dict, List, Optional, Tuple

from .api import fetch_app_name_sync
from .auth import clear_secret_caches
from .config import (
    app_config_lists,
    format_interval_minutes,
    is_placeholder_app_name,
    merge_apps_from_json,
    normalize_json_path,
    random_check_interval,
    save_config,
)
from .ui import get_user_input, print_app_status_lists


def _collect_editable_apps(config: dict) -> List[Tuple[str, dict]]:
    editable = []
    for app in config.get("APPS", []):
        editable.append(("待监控", app))
    for app in config.get("APPROVED_APPS", []):
        editable.append(("已过审", app))
    return editable


def _find_editable_app(config: dict, selector: str) -> Optional[dict]:
    editable = _collect_editable_apps(config)
    if selector.isdigit():
        idx = int(selector) - 1
        if 0 <= idx < len(editable):
            return editable[idx][1]
        return None
    for _, app in editable:
        if app.get("APP_ID") == selector:
            return app
    return None


def _app_id_in_use(config: dict, app_id: str, exclude_id: str = "") -> bool:
    for list_key in ("APPS", "APPROVED_APPS", "REMOVED_APPS"):
        for a in config.get(list_key, []):
            aid = a.get("APP_ID", "")
            if aid == app_id and aid != exclude_id:
                return True
    return False


def edit_single_app(app: dict, config: dict) -> bool:
    app_id = app.get("APP_ID", "")
    app_name = app.get("APP_NAME", f"App({app_id})")
    print(f"\n🔧 修改应用配置: {app_name} (ID: {app_id})")
    changed = False

    new_app_id = get_user_input("👉 App ID", app_id)
    if new_app_id != app_id:
        if not new_app_id.strip().isdigit():
            print("⚠️ App ID 应为数字，已忽略此次修改。")
        elif _app_id_in_use(config, new_app_id, exclude_id=app_id):
            print("⚠️ 该 App ID 已在监控列表中，无法修改为此 ID。")
        else:
            app["APP_ID"] = new_app_id.strip()
            app["APP_NAME"] = f"App({new_app_id.strip()})"
            for key in ("APPROVED_AT", "APPROVED_VERSION", "APPROVED_STATE"):
                app.pop(key, None)
            app_id = new_app_id.strip()
            changed = True

    new_issuer = get_user_input("👉 Issuer ID", app.get("ISSUER_ID", ""))
    if new_issuer != app.get("ISSUER_ID"):
        app["ISSUER_ID"] = new_issuer
        changed = True

    new_key = get_user_input("👉 Key ID", app.get("KEY_ID", ""))
    if new_key != app.get("KEY_ID"):
        app["KEY_ID"] = new_key
        changed = True

    p8_path = app.get("P8_PATH", "")
    if p8_path and os.path.exists(p8_path):
        p8_prompt = (
            f"\n👉 拖入 .p8 密钥 [当前: {os.path.basename(p8_path)}]，直接回车保持不变: "
        )
    else:
        p8_prompt = "\n👉 请拖入 .p8 密钥文件: "
    p8_input = input(p8_prompt).strip()
    if p8_input:
        new_p8 = normalize_json_path(p8_input)
        if os.path.exists(new_p8):
            if new_p8 != app.get("P8_PATH"):
                app["P8_PATH"] = new_p8
                changed = True
        else:
            print(f"❌ 找不到该文件: {new_p8}")

    default_push = app.get("PUSHPLUS_TOKEN") or config.get("DEFAULT_PUSHPLUS", "")
    new_push = get_user_input("👉 PushPlus Token", default_push)
    if new_push != app.get("PUSHPLUS_TOKEN", ""):
        app["PUSHPLUS_TOKEN"] = new_push
        changed = True

    default_feishu = app.get("FEISHU_WEBHOOK") or config.get("DEFAULT_FEISHU", "")
    new_feishu = get_user_input("👉 飞书 Webhook", default_feishu)
    if new_feishu != app.get("FEISHU_WEBHOOK", ""):
        app["FEISHU_WEBHOOK"] = new_feishu
        changed = True

    check_min = str(int(app.get("CHECK_INTERVAL", 600) // 60))
    new_check_min = get_user_input("👉 非审核中轮询间隔(分钟)", check_min)
    try:
        new_check = int(float(new_check_min) * 60)
        if new_check < 60:
            print("⚠️ 轮询间隔不能低于 1 分钟，已自动重置为 10 分钟")
            new_check = 600
    except ValueError:
        new_check = app.get("CHECK_INTERVAL", 600)
    if new_check != app.get("CHECK_INTERVAL"):
        app["CHECK_INTERVAL"] = new_check
        changed = True

    review_min = str(int(app.get("REVIEW_INTERVAL", 180) // 60))
    new_review_min = get_user_input("👉 审核中轮询间隔(分钟)", review_min)
    try:
        new_review = int(float(new_review_min) * 60)
        if new_review < 30:
            print("⚠️ 轮询间隔不能低于 0.5 分钟，已自动重置为 3 分钟")
            new_review = 180
    except ValueError:
        new_review = app.get("REVIEW_INTERVAL", 180)
    if new_review != app.get("REVIEW_INTERVAL"):
        app["REVIEW_INTERVAL"] = new_review
        changed = True

    if is_placeholder_app_name(app.get("APP_NAME", ""), app.get("APP_ID", "")):
        app["APP_NAME"] = f"App({app.get('APP_ID', '')})"

    if changed:
        clear_secret_caches()
    return changed


def interactive_edit_apps(config, apps, config_path: str = None):
    while True:
        editable = _collect_editable_apps(config)
        if not editable:
            print("⚠️ 没有可修改的应用。")
            return

        print_app_status_lists(config)
        print("\n🔧 修改应用配置")
        for i, (tag, app) in enumerate(editable, 1):
            name = app.get("APP_NAME", f"App({app.get('APP_ID')})")
            print(f"  {i}. [{tag}] {name} (ID: {app.get('APP_ID')})")

        sel = input("\n👉 输入序号或 App ID 进行修改，直接回车返回监控: ").strip()
        if not sel:
            print("\n🏃‍♂️ 返回监控...")
            return

        target = _find_editable_app(config, sel)
        if not target:
            print("⚠️ 未找到该应用，请重试。")
            continue

        if edit_single_app(target, config):
            save_config(config, config_path, refresh_names=True)
            print("✅ 配置已保存！下一轮将使用新凭证查询。")
        else:
            print("ℹ️ 未做任何修改。")

        if input("👉 继续修改其他应用? (y/N): ").strip().upper() != "Y":
            print("\n🏃‍♂️ 返回监控...")
            return


def interactive_add_apps(config, apps, config_path: str = None):
    while True:
        if len(apps) > 0 or config.get("APPROVED_APPS"):
            print_app_status_lists(config)
        if len(apps) > 0:
            print("\n📦 待监控应用 (正在刷新名称...):")
            need_save = False
            for i, app in enumerate(apps):
                old_name = app.get("APP_NAME")
                name = fetch_app_name_sync(app)
                if old_name != name:
                    need_save = True
                print(f"  {i + 1}. {name} (ID: {app.get('APP_ID')})")
            if need_save:
                save_config(config, config_path)

            print("\n💡 提示：你可以直接【拖拽】之前归档的 .json 配置文件到这里，免去手动输入。")
            app_id_input = input(
                "👉 请输入待监控的新 App ID (或拖拽 .json 文件)，"
                "M 修改推送，E 修改应用配置，直接回车开始监控: "
            ).strip()
            if not app_id_input:
                print("\n🏃‍♂️ 退出添加模式，即将开始监控...")
                break
            if app_id_input.upper() == "E":
                interactive_edit_apps(config, apps, config_path)
                continue
            if app_id_input.upper() == "M":
                print("\n🔧 修改推送配置：")
                new_pushplus = input(
                    f"👉 粘贴 PushPlus Token [当前: {config.get('DEFAULT_PUSHPLUS', '')}]: "
                ).strip()
                if new_pushplus:
                    config["DEFAULT_PUSHPLUS"] = new_pushplus
                new_feishu = input(
                    f"👉 粘贴飞书 Webhook 地址 [当前: {config.get('DEFAULT_FEISHU', '')}]: "
                ).strip()
                if new_feishu:
                    config["DEFAULT_FEISHU"] = new_feishu
                save_config(config, config_path)
                print("✅ 推送配置已更新！\n")
                continue
        else:
            print("\n--- ➕ 添加新监控应用 ---")
            print("💡 提示：你可以直接【拖拽】之前归档的 .json 配置文件到这里，免去手动输入。")
            app_id_input = input(
                "👉 请输入待监控的 App ID (或拖拽 .json 文件)，M 修改推送，E 修改应用配置: "
            ).strip()
            if not app_id_input:
                print("⚠️ App ID 不能为空！")
                continue
            if app_id_input.upper() == "E":
                interactive_edit_apps(config, apps, config_path)
                continue
            if app_id_input.upper() == "M":
                print("\n🔧 修改推送配置：")
                new_pushplus = input(
                    f"👉 粘贴 PushPlus Token [当前: {config.get('DEFAULT_PUSHPLUS', '')}]: "
                ).strip()
                if new_pushplus:
                    config["DEFAULT_PUSHPLUS"] = new_pushplus
                new_feishu = input(
                    f"👉 粘贴飞书 Webhook 地址 [当前: {config.get('DEFAULT_FEISHU', '')}]: "
                ).strip()
                if new_feishu:
                    config["DEFAULT_FEISHU"] = new_feishu
                save_config(config, config_path)
                print("✅ 推送配置已更新！\n")
                continue

        default_issuer_id = apps[-1].get("ISSUER_ID", "") if apps else ""
        default_p8 = apps[-1].get("P8_PATH", "") if apps else ""
        default_pushplus = config.get("DEFAULT_PUSHPLUS", "")
        default_feishu = config.get("DEFAULT_FEISHU", "")
        app_id_input = normalize_json_path(app_id_input)

        if app_id_input.endswith(".json") and os.path.exists(app_id_input):
            try:
                added_count = merge_apps_from_json(app_id_input, apps, config)
                if added_count > 0:
                    config["APPS"] = apps
                    save_config(config, config_path, refresh_names=True)
                    print(f"✅ 成功从配置文件加载了 {added_count} 个应用！")
                else:
                    print("⚠️ 配置文件中没有发现新的有效应用，或应用已存在。")
                continue
            except Exception as e:
                print(f"❌ 解析拖拽的配置文件失败: {e}")
                continue

        app_id = app_id_input
        if not app_id:
            print("⚠️ App ID 不能为空！")
            continue

        if "REMOVED_APPS" in app_config_lists(config, app_id):
            print("⚠️ 该应用已在「已下架」列表中。下架为终态，不会重新上架，无需再监控。")
            continue
        if "APPROVED_APPS" in app_config_lists(config, app_id):
            print("⚠️ 该应用已在「已过审」列表中，正在持续监控。")
            continue

        existing = next((a for a in apps if a.get("APP_ID") == app_id), None)
        if existing:
            print("⚠️ 这个 App ID 已经在监控列表里了。")
            if input("👉 输入 Y 修改该应用配置: ").strip().upper() == "Y":
                if edit_single_app(existing, config):
                    save_config(config, config_path, refresh_names=True)
                    print("✅ 配置已保存！")
            continue

        issuer_id = get_user_input("👉 请输入 Issuer ID", default_issuer_id)
        key_id = get_user_input("👉 请输入 Key ID", "")

        if default_p8 and os.path.exists(default_p8):
            prompt_str = "\n👉 请拖入对应的 .p8 文件 [当前已有缓存路径，直接回车复用该密钥]: "
        else:
            prompt_str = "\n👉 请直接将您的 .p8 密钥文件【拖拽】到这个终端窗口中，然后按回车键："

        user_input = input(prompt_str).strip()
        p8_path = default_p8
        if user_input:
            p8_path = user_input.strip("'").strip('"').replace("\\ ", " ")

        if not os.path.exists(p8_path):
            print(f"❌ 找不到该文件: {p8_path}")
            continue

        if not default_pushplus and not default_feishu:
            print("\n💡 【首次设置】过审或状态变化时通过推送通知（可选）")
            default_pushplus = input("👉 粘贴 PushPlus Token (直接回车跳过): ").strip()
            if default_pushplus:
                config["DEFAULT_PUSHPLUS"] = default_pushplus

            default_feishu = input("👉 粘贴飞书 Webhook 地址 (直接回车跳过): ").strip()
            if default_feishu:
                config["DEFAULT_FEISHU"] = default_feishu

        pushplus_token = default_pushplus
        feishu_webhook = default_feishu

        suggested_check = random_check_interval()
        check_interval_min = get_user_input(
            "\n👉 请输入该应用在非「正在审核」状态下的轮询间隔(分钟)",
            format_interval_minutes(suggested_check),
        )
        try:
            check_interval = int(float(check_interval_min) * 60)
            if check_interval < 60:
                print("⚠️ 轮询间隔不能低于 1 分钟，已自动重置为 10 分钟")
                check_interval = 600
        except ValueError:
            check_interval = suggested_check

        review_interval_min = get_user_input("👉 请输入该应用在「正在审核」状态下的轮询间隔(分钟)", "3")
        try:
            review_interval = int(float(review_interval_min) * 60)
            if review_interval < 30:
                print("⚠️ 轮询间隔不能低于 0.5 分钟，已自动重置为 3 分钟")
                review_interval = 180
        except ValueError:
            review_interval = 180

        new_app = {
            "APP_ID": app_id,
            "ISSUER_ID": issuer_id,
            "KEY_ID": key_id,
            "P8_PATH": p8_path,
            "PUSHPLUS_TOKEN": pushplus_token,
            "FEISHU_WEBHOOK": feishu_webhook,
            "APP_NAME": f"App({app_id})",
            "CHECK_INTERVAL": check_interval,
            "REVIEW_INTERVAL": review_interval,
        }

        apps.append(new_app)
        config["APPS"] = apps
        print("✅ 应用已加入监控列表！")
        print(
            f"   ⏱️  轮询间隔: 非审核 {format_interval_minutes(check_interval)} 分钟 / "
            f"审核中 {format_interval_minutes(review_interval)} 分钟"
        )
        save_config(config, config_path)
