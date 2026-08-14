import os
from typing import Optional

from .auth import make_token, read_p8_key
from .constants import APPROVED_STATES, DELISTED_STATES
from .session import apple_headers, get_aux_session, get_session, get_with_backoff, jitter


def apple_error_detail(resp) -> str:
    try:
        body = resp.json()
        errs = body.get("errors") or []
        parts = []
        for e in errs[:3]:
            d = e.get("detail") or e.get("title") or str(e)
            if d:
                parts.append(str(d))
        return " | ".join(parts) if parts else ""
    except Exception:
        return (resp.text or "")[:200]


def fetch_app_name_sync(app: dict) -> str:
    app_id = app.get("APP_ID", "")
    app_name = app.get("APP_NAME", "")
    if app_name and app_name != f"App({app_id})" and app_name != "未知":
        return app_name

    issuer_id = app.get("ISSUER_ID")
    key_id = app.get("KEY_ID")
    p8_path = app.get("P8_PATH")

    if not (issuer_id and key_id and p8_path and os.path.exists(p8_path)):
        return app_name or f"App({app_id})"

    try:
        private_key = read_p8_key(p8_path)
        token = make_token(issuer_id, key_id, private_key)
        jitter()
        res = get_session().get(
            f"https://api.appstoreconnect.apple.com/v1/apps/{app_id}",
            headers=apple_headers(token),
            timeout=5,
        )
        if res.status_code == 200:
            fetched_name = res.json().get("data", {}).get("attributes", {}).get("name")
            if fetched_name:
                app["APP_NAME"] = fetched_name
                return fetched_name
    except Exception:
        pass
    return app_name or f"App({app_id})"


def version_store_state(attributes: dict) -> str:
    """兼容 appStoreState（旧）与 appVersionState（新）。"""
    if not attributes:
        return "UNKNOWN_STATE"
    return (
        attributes.get("appStoreState")
        or attributes.get("appVersionState")
        or "UNKNOWN_STATE"
    )


def pick_monitor_version(versions: list, preferred_version: Optional[str] = None) -> Optional[dict]:
    """
    选择用于监控的版本，避免只取 versions[0] 漏掉已上架/已下架版本。
    优先级：记录版本 → 下架态 → 已上架态 → 其余第一个。
    """
    if not versions:
        return None

    if preferred_version:
        for v in versions:
            vs = (v.get("attributes") or {}).get("versionString")
            if vs and str(vs) == str(preferred_version):
                return v

    delisted = []
    approved = []
    for v in versions:
        st = version_store_state(v.get("attributes") or {})
        if st in DELISTED_STATES:
            delisted.append(v)
        elif st in APPROVED_STATES:
            approved.append(v)

    if delisted:
        return delisted[0]
    if approved:
        return approved[0]
    return versions[0]


def find_delisted_version(versions: list) -> Optional[dict]:
    """在返回的版本列表中查找任一已下架状态。"""
    for v in versions or []:
        st = version_store_state(v.get("attributes") or {})
        if st in DELISTED_STATES:
            return v
    return None


def check_itunes_store_presence(app_id: str) -> Optional[bool]:
    """
    通过 iTunes Lookup 判断应用是否仍在商店可见。
    True=在架，False=cn/us 均查无，None=探测失败（勿当下来结论）。
    封号/强制下架后常仍能在 ASC 看到 READY_FOR_SALE，但商店页已消失。
    """
    if not app_id:
        return None
    session = get_aux_session()
    empty_ok = 0
    for country in ("cn", "us"):
        try:
            url = f"https://itunes.apple.com/{country}/lookup?id={app_id}"
            resp = session.get(url, timeout=12)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if int(data.get("resultCount") or 0) > 0:
                return True
            empty_ok += 1
        except Exception:
            return None
    if empty_ok >= 2:
        return False
    return None


def check_asc_territory_for_sale(app_id: str, headers: dict) -> Optional[bool]:
    """
    读取 ASC v2 区域可售性。True=至少一区可售，False=明确不可售，None=无法判断。
    开发者下架后版本状态可能仍是 READY_FOR_SALE，需用此接口辅助。
    """
    if not app_id:
        return None
    url = (
        f"https://api.appstoreconnect.apple.com/v2/appAvailabilities/{app_id}"
        f"/territoryAvailabilities?limit=200"
    )
    try:
        jitter()
        resp = get_with_backoff(url, headers)
    except Exception:
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        return None
    try:
        items = resp.json().get("data") or []
    except Exception:
        return None
    if not items:
        return False

    any_available = False
    any_cannot_sell = False
    for item in items:
        attrs = item.get("attributes") or {}
        if attrs.get("available") is True:
            any_available = True
        statuses = attrs.get("contentStatuses") or []
        if "CANNOT_SELL" in statuses:
            any_cannot_sell = True

    if any_available:
        return True
    if any_cannot_sell or all(
        (it.get("attributes") or {}).get("available") is False for it in items
    ):
        return False
    return None
