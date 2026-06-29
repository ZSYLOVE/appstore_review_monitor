import random
import sys
import time

from curl_cffi import requests

from .constants import CHROME_BASE_HEADERS, DEFAULT_IMPERSONATE_TARGET

_APPLE_SESSION: requests.Session = None  # type: ignore
_AUX_SESSION: requests.Session = None  # type: ignore

_PROXY_URL = ""
_IMPERSONATE = DEFAULT_IMPERSONATE_TARGET
_STRICT_PROXY = False
_BASE_HEADERS = dict(CHROME_BASE_HEADERS)
_CHROME_VERSION = ""


def configure_session(
    *,
    proxy_url: str = "",
    impersonate: str = DEFAULT_IMPERSONATE_TARGET,
    strict_proxy: bool = False,
    base_headers: dict = None,
) -> None:
    global _PROXY_URL, _IMPERSONATE, _STRICT_PROXY, _BASE_HEADERS, _CHROME_VERSION
    _PROXY_URL = proxy_url or ""
    _IMPERSONATE = impersonate or DEFAULT_IMPERSONATE_TARGET
    _STRICT_PROXY = bool(strict_proxy)
    if base_headers is not None:
        _BASE_HEADERS = dict(base_headers)
        ua = _BASE_HEADERS.get("user-agent", "")
        if "Chrome/" in ua:
            _CHROME_VERSION = ua.split("Chrome/", 1)[1].split(" ", 1)[0]
        else:
            _CHROME_VERSION = ""
    if _STRICT_PROXY and not _PROXY_URL:
        print("❌ STRICT_PROXY 已启用，必须配置有效代理，禁止直连 Apple API。")
        sys.exit(1)
    rebuild_sessions()


def rebuild_session(proxy_url: str = "", impersonate: str = None) -> None:
    """兼容旧接口；等价于 configure_session + rebuild_sessions。"""
    configure_session(
        proxy_url=proxy_url,
        impersonate=impersonate or _IMPERSONATE,
        strict_proxy=_STRICT_PROXY,
        base_headers=_BASE_HEADERS,
    )


def rebuild_sessions() -> None:
    global _APPLE_SESSION, _AUX_SESSION
    apple_proxies = {"http": _PROXY_URL, "https": _PROXY_URL} if _PROXY_URL else None
    _APPLE_SESSION = requests.Session(impersonate=_IMPERSONATE, proxies=apple_proxies)
    # 第三方通知：独立 Session，不走 Chrome 指纹伪装，直连
    _AUX_SESSION = requests.Session()


def get_apple_session() -> requests.Session:
    if _APPLE_SESSION is None:
        rebuild_sessions()
    return _APPLE_SESSION


def get_aux_session() -> requests.Session:
    if _AUX_SESSION is None:
        rebuild_sessions()
    return _AUX_SESSION


def get_session() -> requests.Session:
    return get_apple_session()


def get_impersonate_target() -> str:
    return _IMPERSONATE


def get_apple_base_headers() -> dict:
    return dict(_BASE_HEADERS)


def get_chrome_version() -> str:
    return _CHROME_VERSION


def is_strict_proxy() -> bool:
    return _STRICT_PROXY


def validate_apple_connectivity(timeout: int = 12) -> tuple:
    """探测 Apple API 是否可达（401 亦视为连通）。返回 (成功与否, 详情)。"""
    if not _PROXY_URL:
        if _STRICT_PROXY:
            return False, "未配置代理"
        return True, "未启用连通性检查（非严格模式）"
    try:
        resp = get_apple_session().get(
            "https://api.appstoreconnect.apple.com/v1/apps?limit=1",
            timeout=timeout,
        )
        if resp.status_code in (200, 401, 403):
            return True, f"HTTP {resp.status_code}"
        return False, f"HTTP {resp.status_code}: {(resp.text or '')[:120]}"
    except Exception as e:
        return False, str(e)


def validate_apple_proxy(timeout: int = 12) -> bool:
    ok, _ = validate_apple_connectivity(timeout=timeout)
    return ok


def apple_headers(token: str) -> dict:
    h = dict(_BASE_HEADERS)
    h["content-type"] = "application/json"
    h["origin"] = "https://appstoreconnect.apple.com"
    h["referer"] = "https://appstoreconnect.apple.com/"
    h["sec-fetch-site"] = "same-site"
    h["authorization"] = f"Bearer {token}"
    return h


def jitter(base_ms: int = 800) -> None:
    time.sleep(base_ms / 1000 + random.uniform(0.1, 0.6))


def http_should_retry(status: int) -> bool:
    return status == 429 or (500 <= status <= 599)


def sleep_backoff(attempt: int, base: float = 1.5) -> None:
    delay = min(90.0, base * (2 ** attempt)) + random.uniform(0, 0.4)
    time.sleep(delay)


def get_with_backoff(
    url: str,
    headers: dict,
    *,
    timeout: int = 15,
    max_attempts: int = 5,
):
    last = None
    session = get_apple_session()
    for attempt in range(max_attempts):
        if attempt > 0:
            jitter(150)
        try:
            last = session.get(url, headers=headers, timeout=timeout)
        except Exception as e:
            if _STRICT_PROXY:
                raise RuntimeError(f"STRICT_PROXY: 代理请求失败: {e}") from e
            raise
        sc = last.status_code
        if sc == 200:
            return last
        if sc in (400, 401, 403, 404):
            return last
        if http_should_retry(sc) and attempt < max_attempts - 1:
            print(f"  ⏳ 苹果接口返回 {sc}，退避后重试 ({attempt + 1}/{max_attempts - 1})...")
            sleep_backoff(attempt)
            continue
        return last
    return last
