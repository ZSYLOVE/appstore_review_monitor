import os

from .auth import make_token, read_p8_key
from .session import apple_headers, get_session, jitter


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
