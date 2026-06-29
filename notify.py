import os
import platform
import subprocess

from .session import get_aux_session
from .ui import monitor_print


def escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def mac_notification(title: str, message: str) -> None:
    if platform.system() != "Darwin":
        return
    script = (
        f'display notification "{escape_applescript(message)}" '
        f'with title "{escape_applescript(title)}"'
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def play_sound(sound_name: str) -> None:
    if platform.system() != "Darwin":
        return
    sound_path = f"/System/Library/Sounds/{sound_name}.aiff"
    if os.path.exists(sound_path):
        subprocess.Popen(
            ["afplay", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def send_pushplus(token, title, content):
    if not token:
        return
    monitor_print("\n📲 正在尝试通过 PushPlus 发送微信通知...")
    url = "http://www.pushplus.plus/send"
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    unique_content = (
        f"{content}<br><br><hr>"
        f"<small style='color:gray;'>监控时间: {current_time}</small>"
    )
    data = {"token": token, "title": title, "content": unique_content, "template": "html"}
    try:
        res = get_aux_session().post(url, json=data, timeout=10)
        if res.status_code == 200 and res.json().get("code") == 200:
            monitor_print("✅ 微信推送成功！请查看您的手机微信。")
        else:
            monitor_print(f"⚠️ 微信推送失败: {res.text}")
    except Exception as e:
        monitor_print(f"⚠️ 网络原因导致微信推送失败: {e}")


def send_feishu(webhook_url, title, content):
    if not webhook_url:
        return
    monitor_print("\n📲 正在尝试通过飞书发送通知...")
    from datetime import datetime

    text_content = (
        content
        .replace("<br>", "\n").replace("<b>", "").replace("</b>", "")
        .replace("<h3>", "").replace("</h3>", "").replace("<p>", "")
        .replace("</p>", "\n").replace("<hr>", "---")
        .replace("<small style='color:gray;'>", "").replace("</small>", "")
        .replace("<b style='color:#007AFF'>", "")
    )
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_text = f"{title}\n\n{text_content}\n---\n监控时间: {current_time}"

    is_flow_webhook = "trigger-webhook" in webhook_url
    if is_flow_webhook:
        data = {"title": title, "content": text_content, "timestamp": current_time, "full_message": final_text}
    else:
        data = {"msg_type": "text", "content": {"text": final_text}}

    try:
        res = get_aux_session().post(webhook_url, json=data, timeout=10)
        if res.status_code == 200 and res.json().get("code") == 0:
            monitor_print("✅ 飞书推送成功！请查看您的飞书群。")
        else:
            monitor_print(f"⚠️ 飞书推送失败: {res.text}")
    except Exception as e:
        monitor_print(f"⚠️ 网络原因导致飞书推送失败: {e}")


def notify_status_change(app_id, app_name, old_state, new_state, pushplus_token, feishu_webhook):
    play_sound("Pop")
    short_new_state = new_state.split("(")[0].strip()
    mac_notification("App 状态变更 🔄", f"【{app_name}】{short_new_state}")
    title = f"🔄 【{app_name}】状态变更为: {short_new_state}"
    content = (
        f"<h3>🔄 状态更新</h3><p>您的 App <b>【{app_name}】</b>(ID: {app_id}) 状态发生了变化：</p>"
        f"<p>从 <b>{old_state}</b><br>变更为 👉 <b style='color:#007AFF'>{new_state}</b></p>"
    )
    if pushplus_token:
        send_pushplus(pushplus_token, title, content)
    if feishu_webhook:
        send_feishu(feishu_webhook, title, content)


def notify_version_change(
    app_id, app_name, old_version, new_version, new_state, pushplus_token, feishu_webhook
):
    play_sound("Pop")
    mac_notification("App 新版本 📦", f"【{app_name}】{old_version} → {new_version}")
    title = f"📦 【{app_name}】检测到新版本: {new_version}"
    content = (
        f"<h3>📦 新版本</h3><p>您的 App <b>【{app_name}】</b>(ID: {app_id}) 版本已更新：</p>"
        f"<p>从 <b>v{old_version}</b> → <b>v{new_version}</b></p>"
        f"<p>当前状态: <b>{new_state}</b></p>"
    )
    if pushplus_token:
        send_pushplus(pushplus_token, title, content)
    if feishu_webhook:
        send_feishu(feishu_webhook, title, content)


def notify_delisted(app_id, app_name, version_string, pushplus_token, feishu_webhook):
    mac_notification(
        "App 已下架 ❌",
        f"您的 App【{app_name}】v{version_string} 已从 App Store 下架。",
    )
    play_sound("Basso")
    title = f"❌ 【{app_name}】已下架"
    content = (
        f"<h3>❌ 应用已下架</h3><p>您的 App <b>【{app_name}】</b>(ID: {app_id}) "
        f"v{version_string} 已从 App Store 下架。</p>"
        f"<p>请登录 App Store Connect 查看详情。</p>"
    )
    if pushplus_token:
        send_pushplus(pushplus_token, title, content)
    if feishu_webhook:
        send_feishu(feishu_webhook, title, content)


def notify_rejected(app_id, app_name, pushplus_token, feishu_webhook):
    mac_notification(
        "App 审核被拒 🔴",
        f"抱歉，您的 App【{app_name}】被苹果拒绝了，请查看邮箱或 App Store Connect。",
    )
    play_sound("Basso")
    title = f"🔴 【{app_name}】审核被拒！"
    content = (
        f"<h3>🔴 审核被拒！</h3><p>您的 App <b>【{app_name}】</b>(ID: {app_id}) 刚刚被苹果拒绝了。</p>"
        f"<p>请尽快登录 App Store Connect 查看「解决中心」的详细原因并进行修改。</p>"
    )
    if pushplus_token:
        send_pushplus(pushplus_token, title, content)
    if feishu_webhook:
        send_feishu(feishu_webhook, title, content)


def notify_success(app_id, app_name, pushplus_token, feishu_webhook):
    mac_notification(
        "App 审核通过 🎉",
        f"恭喜，您的 App【{app_name}】已经通过苹果审核上架啦！",
    )
    play_sound("Glass")
    title = f"🎉 【{app_name}】审核通过啦！"
    content = (
        f"<h3>🎉 恭喜！审核通过！</h3><p>您的 App <b>【{app_name}】</b>(ID: {app_id}) "
        f"已经通过苹果审核并且上架啦！</p><p>快去 App Store 看看吧！</p>"
    )
    if pushplus_token:
        send_pushplus(pushplus_token, title, content)
    if feishu_webhook:
        send_feishu(feishu_webhook, title, content)
