import os
import time

import jwt

from .constants import TOKEN_REFRESH_MARGIN, TOKEN_TTL_SECONDS

_TOKEN_CACHE: dict = {}
_P8_KEY_CACHE: dict = {}


def read_p8_key(p8_path: str) -> str:
    mtime = os.path.getmtime(p8_path)
    cached = _P8_KEY_CACHE.get(p8_path)
    if cached and cached[1] == mtime:
        return cached[0]
    with open(p8_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    _P8_KEY_CACHE[p8_path] = (content, mtime)
    return content


def make_token(issuer_id: str, key_id: str, private_key: str) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "aud": "appstoreconnect-v1",
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"alg": "ES256", "kid": key_id})


def get_token_for_app(app: dict) -> str:
    issuer_id = app["ISSUER_ID"]
    key_id = app["KEY_ID"]
    private_key = read_p8_key(app["P8_PATH"])
    cache_key = (issuer_id, key_id)
    now = int(time.time())
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached[1] - TOKEN_REFRESH_MARGIN > now:
        return cached[0]
    token = make_token(issuer_id, key_id, private_key)
    _TOKEN_CACHE[cache_key] = (token, now + TOKEN_TTL_SECONDS)
    return token


def clear_secret_caches() -> None:
    """进程退出前清空内存中的 JWT 与 P8 缓存。"""
    _TOKEN_CACHE.clear()
    _P8_KEY_CACHE.clear()
