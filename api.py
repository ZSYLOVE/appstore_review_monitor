import os
from typing import Optional, Tuple

from .auth import make_token, read_p8_key
from .constants import APPROVED_STATES, DELISTED_STATES, PIPELINE_STATES, REJECTED_STATES
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
    """
    兼容 appStoreState（旧）与 appVersionState（新）。
    苹果已移除「Removed from Sale」版本态；下架后常仍为 READY_FOR_SALE / READY_FOR_DISTRIBUTION。
    """
    if not attributes:
        return "UNKNOWN_STATE"
    old = attributes.get("appStoreState")
    new = attributes.get("appVersionState")
    # 旧字段若仍带下架态，优先采用
    if old in DELISTED_STATES:
        return old
    if old:
        return old
    return new or "UNKNOWN_STATE"


def pick_monitor_version(
    versions: list,
    preferred_version: Optional[str] = None,
    *,
    purpose: str = "pending",
) -> Optional[dict]:
    """
    选择用于监控的版本。
    - pending：必须跟住所跟踪/审核中的版本，绝不能因存在旧的 READY_FOR_SALE 而误报过审
    - approved：优先记录版本 / 下架 / 在架版本
    """
    if not versions:
        return None

    def _state(v: dict) -> str:
        return version_store_state(v.get("attributes") or {})

    def _ver(v: dict) -> str:
        return str((v.get("attributes") or {}).get("versionString") or "")

    if preferred_version:
        for v in versions:
            if _ver(v) != str(preferred_version):
                continue
            st = _state(v)
            if st == "REPLACED_WITH_NEW_VERSION":
                break
            # 待监控：只要还是这个版本号就继续跟，哪怕仍在审/被拒
            if purpose == "pending":
                return v
            if st in APPROVED_STATES or st in DELISTED_STATES:
                return v
            break

    by_state = {}
    for v in versions:
        by_state.setdefault(_state(v), []).append(v)

    if purpose == "approved":
        for st in DELISTED_STATES:
            if by_state.get(st):
                return by_state[st][0]
        for st in APPROVED_STATES:
            if by_state.get(st):
                return by_state[st][0]
        return versions[0]

    # pending：审核管线 > 被拒 > 已上架（仅当没有在审版本，例如首次过审）
    for st in PIPELINE_STATES:
        if by_state.get(st):
            return by_state[st][0]
    for st in REJECTED_STATES:
        if by_state.get(st):
            return by_state[st][0]
    for st in APPROVED_STATES:
        if by_state.get(st):
            return by_state[st][0]
    return versions[0]


def find_delisted_version(versions: list) -> Optional[dict]:
    """在返回的版本列表中查找任一已下架状态（旧 API 字段）。"""
    for v in versions or []:
        st = version_store_state(v.get("attributes") or {})
        if st in DELISTED_STATES:
            return v
    return None


def _itunes_lookup_result_count(session, url: str) -> Optional[int]:
    try:
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return int(data.get("resultCount") or 0)
    except Exception:
        return None


def check_itunes_store_presence(app_id: str) -> Optional[bool]:
    """
    通过 iTunes Lookup 判断应用是否仍在商店可见。
    True=在架，False=cn/us 均查无，None=探测失败（勿当下来结论）。
    封号/强制下架/开发者下架后，ASC 版本态常仍显示可供分发，但商店页会消失。
    """
    if not app_id:
        return None
    try:
        session = get_aux_session()
    except Exception:
        session = None
    if session is None:
        return None

    empty_ok = 0
    urls = [
        f"https://itunes.apple.com/cn/lookup?id={app_id}",
        f"https://itunes.apple.com/us/lookup?id={app_id}",
    ]
    for url in urls:
        count = _itunes_lookup_result_count(session, url)
        if count is None:
            # 无国家路径再试一次
            fallback = f"https://itunes.apple.com/lookup?id={app_id}&country={url.split('/')[3]}"
            count = _itunes_lookup_result_count(session, fallback)
        if count is None:
            return None
        if count > 0:
            return True
        empty_ok += 1
    if empty_ok >= 2:
        return False
    return None


def check_asc_territory_for_sale(app_id: str, headers: dict) -> Optional[bool]:
    """
    读取 ASC 区域可售性。True=至少一区可售，False=明确不可售，None=无法判断。
    开发者下架后版本状态可能仍是 READY_FOR_SALE / READY_FOR_DISTRIBUTION。
    """
    if not app_id:
        return None

    candidates = [
        (
            f"https://api.appstoreconnect.apple.com/v2/appAvailabilities/{app_id}"
            f"/territoryAvailabilities?limit=200"
        ),
        (
            f"https://api.appstoreconnect.apple.com/v1/apps/{app_id}/appAvailability"
        ),
    ]
    items = None
    for url in candidates:
        try:
            jitter()
            resp = get_with_backoff(url, headers)
        except Exception:
            continue
        if resp.status_code == 404:
            continue
        if resp.status_code != 200:
            continue
        try:
            body = resp.json()
        except Exception:
            continue
        data = body.get("data")
        if isinstance(data, list):
            items = data
            break
        if isinstance(data, dict):
            # v1 appAvailability 单对象：再拉 territory 关系或看 attributes
            rel = (data.get("relationships") or {}).get("territoryAvailabilities") or {}
            rel_id = (data.get("id") or app_id)
            turl = (
                f"https://api.appstoreconnect.apple.com/v2/appAvailabilities/{rel_id}"
                f"/territoryAvailabilities?limit=200"
            )
            try:
                jitter()
                tresp = get_with_backoff(turl, headers)
                if tresp.status_code == 200:
                    items = tresp.json().get("data") or []
                    break
            except Exception:
                pass
            attrs = data.get("attributes") or {}
            if "availableInNewTerritories" in attrs and not items:
                # 无分区明细时无法可靠判断，继续尝试其它端点
                continue
    if items is None:
        return None
    if not items:
        # 空列表常见于权限/端点不匹配，不能当成已下架
        return None

    sellable = 0
    cannot_sell = 0
    for item in items:
        attrs = item.get("attributes") or {}
        statuses = set(attrs.get("contentStatuses") or [])
        if "CANNOT_SELL" in statuses:
            cannot_sell += 1
            continue
        if attrs.get("available") is True or "AVAILABLE" in statuses:
            sellable += 1
        elif attrs.get("available") is False:
            continue
        elif statuses & {
            "AVAILABLE_FOR_PREORDER",
            "AVAILABLE_FOR_PREORDER_ON_DATE",
            "PROCESSING_TO_AVAILABLE",
        }:
            sellable += 1

    if sellable > 0:
        return True
    # 有分区数据且全部不可售，才判定不在架
    if cannot_sell > 0 or all(
        (it.get("attributes") or {}).get("available") is False for it in items
    ):
        return False
    return None


def detect_off_store(
    app_id: str, headers: dict
) -> Tuple[Optional[bool], str]:
    """
    综合 ASC 可售性 + iTunes 公开页判断是否已不在架。
    返回 (True, reason) / (False, '') / (None, 说明)。
    以下架归档为准时：以商店公开页为准；ASC 单独不可售不直接归档（易误杀）。
    """
    for_sale = check_asc_territory_for_sale(app_id, headers)
    present = check_itunes_store_presence(app_id)

    if present is False and for_sale is False:
        return True, "ASC 各地区不可售，且 App Store 公开页查无"
    if present is False:
        return True, "App Store 公开页查无（可能封号或强制下架）"
    if for_sale is False and present is True:
        # 可售性接口偶发误报，商店仍在架则继续观察
        return False, ""
    if for_sale is False and present is None:
        return None, "ASC 显示不可售，但商店页探测失败，暂不下架结论"
    if for_sale is None and present is None:
        return None, "在架探测失败（ASC 可售性与商店页均不可用）"
    return False, ""
