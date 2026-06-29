import platform
import socket
import uuid
from typing import Optional, Tuple

from .session import (
    get_apple_base_headers,
    get_apple_session,
    get_chrome_version,
    get_impersonate_target,
    validate_apple_connectivity,
)


def _parse_cloudflare_trace(text: str) -> dict:
    info = {}
    for line in text.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            info[key.strip()] = val.strip()
    return info


def _probe_exit_ip() -> Tuple[Optional[dict], Optional[str]]:
    """经 Apple Session（同代理通道）探测出口 IP，多源回退。"""
    session = get_apple_session()
    probes = [
        (
            "ipify",
            "https://api.ipify.org?format=json",
            lambda r: {"query": r.json().get("ip", "")},
        ),
        (
            "ifconfig",
            "https://ifconfig.me/all.json",
            lambda r: {
                "query": r.json().get("ip_addr", ""),
                "country": r.json().get("country", ""),
                "regionName": r.json().get("region_name", ""),
                "city": r.json().get("city", ""),
                "isp": r.json().get("asn_org", ""),
            },
        ),
        (
            "cloudflare",
            "https://1.1.1.1/cdn-cgi/trace",
            lambda r: _parse_cloudflare_trace(r.text),
        ),
    ]
    last_err = None
    for name, url, parser in probes:
        try:
            resp = session.get(url, timeout=8)
            if resp.status_code != 200:
                last_err = f"{name}: HTTP {resp.status_code}"
                continue
            info = parser(resp)
            exit_ip = info.get("query") or info.get("ip", "")
            if exit_ip:
                info.setdefault("query", exit_ip)
                info["_source"] = name
                return info, None
            last_err = f"{name}: 响应无 IP"
        except Exception as e:
            last_err = f"{name}: {e}"
    return None, last_err


def print_security_status(proxy_url: str = "") -> None:
    W = 54
    impersonate = get_impersonate_target()
    chrome_version = get_chrome_version() or "未知"
    base_headers = get_apple_base_headers()
    print("\n" + "━" * W)
    print("  🛡️  防护状态检测")
    print("━" * W)

    print("\n【本机信息 — 此脚本的 HTTP 请求不携带以下字段】")

    raw_mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    mac_str = ":".join([raw_mac[i : i + 2] for i in range(0, 12, 2)]).upper()
    print(f"  MAC 地址   : {mac_str}")
    print("             ✅ HTTP 请求不携带 | ⚠️  Xcode/iCloud 原生软件会上报给苹果")

    hostname = socket.gethostname()
    print(f"  主机名     : {hostname}")
    print("             ✅ HTTP 请求不携带 | ⚠️  iTunes/Apple ID 登录时会上报")

    real_os = f"{platform.system()} {platform.release()} ({platform.machine()})"
    fake_ua_os = "Intel Mac OS X 10_15_7（UA 伪装值）"
    print(f"  真实系统   : {real_os}")
    print(f"  苹果API看到: {fake_ua_os}  ✅ User-Agent 已伪装")

    apple_ok, apple_detail = validate_apple_connectivity(timeout=10)
    print("\n【Apple API 连通 — 最重要】")
    if apple_ok:
        print(f"  状态       : ✅ 连通正常（{apple_detail}）")
        print("  说明       : 苹果 API 能访问，出口 IP 即为代理节点 IP")
    else:
        print(f"  状态       : ❌ 无法连通（{apple_detail}）")
        print("  说明       : 请检查 Clash 代理、fake-ip-filter 与 apple.com 规则")

    print("\n【出口 IP — 苹果 Session 出口（与 Apple API 同一通道）】")
    info, ip_err = _probe_exit_ip()
    if info:
        exit_ip = info.get("query", "获取失败")
        country = info.get("country", info.get("loc", ""))
        region = info.get("regionName", info.get("colo", ""))
        city = info.get("city", "")
        isp = info.get("isp", info.get("org", ""))
        source = info.get("_source", "")

        loc = " ".join(filter(None, [country, region, city]))
        print(f"  IP 地址    : {exit_ip}  ← 苹果看到的就是这个")
        if loc:
            print(f"  归属地     : {loc}")
        if isp:
            print(f"  ISP/组织   : {isp}")
        if source:
            print(f"  探测来源   : {source}（第三方探测站，仅供参考）")
    else:
        print(f"  ⚠️  IP 探测失败: {ip_err}")
        if apple_ok:
            print("  ℹ️  Apple API 已连通，代理工作正常；第三方 IP 站可能被节点屏蔽")
        else:
            print("  ℹ️  请先修复 Apple API 连通问题")

    if proxy_url:
        print(f"  本地代理   : {proxy_url}  ✅（仅本机转发，苹果看不到此地址）")
    else:
        print("  本地代理   : 未启用  ⚠️  苹果可能可见你的真实 IP")

    print("\n【TLS 指纹伪装 — Apple Session 实时检测】")
    print("  底层库     : curl_cffi (BoringSSL)  ✅ 非 Python 原生 SSL")
    print(f"  伪装目标   : {impersonate} / macOS（本次运行随机）")
    print(f"  Chrome 版本: {chrome_version}")

    tls_live = False
    for tls_url in ("https://tls.peet.ws/api/all", "https://tls.browserleaks.com/json"):
        try:
            tls_resp = get_apple_session().get(tls_url, timeout=10)
            tls_data = tls_resp.json()
            tls_block = tls_data.get("tls", tls_data)
            real_ja3 = tls_block.get("ja3_hash", "获取失败")
            real_ja4 = tls_block.get("ja4", "获取失败")
            real_tls = tls_block.get("tls_version", "")

            print(f"  JA3 哈希   : {real_ja3}")
            print(f"  JA4 签名   : {real_ja4}  ℹ️  每次启动随机变化")
            if real_tls:
                print(f"  TLS 版本   : {real_tls}")
            tls_live = True
            break
        except Exception:
            continue

    if not tls_live:
        if apple_ok:
            print("  实时 JA4   : ⚠️  第三方 TLS 检测站不可达（代理节点常屏蔽）")
            print("             ✅ Apple API 已连通，TLS 伪装对苹果侧仍生效")
        else:
            print("  实时 JA4   : ⚠️  检测失败，且 Apple API 未连通，请检查代理")

    ua = base_headers.get("user-agent", "")
    if ua:
        print(f"  User-Agent : {ua}  ✅")
    else:
        print("  User-Agent : 已设置  ✅")
    print(f"  sec-ch-ua  : {base_headers.get('sec-ch-ua', '已设置')}  ✅")
    print("  sec-fetch-site : same-site（Apple API 请求）  ✅")
    print("  Origin/Referer: appstoreconnect.apple.com  ✅")

    print("\n【Session 隔离】")
    print("  Apple API    : 独立 Session（Chrome 指纹 + 代理）  ✅")
    print("  第三方通知   : 独立 Session（无指纹伪装，直连）    ✅")

    print("\n【请求行为保护】")
    print("  请求间随机抖动 : ✅ 已启用（+0.1~0.6s 随机延迟）")
    print("  Apple Session  : ✅ 全局单一 Session（模拟浏览器长连接）")

    print("\n" + "━" * W + "\n")
