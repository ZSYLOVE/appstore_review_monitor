import random
import re
from typing import Dict

# curl_cffi 桌面版 Chrome 伪装池（排除 android）
_CHROME_DESKTOP_POOL = (
    "chrome136",
    "chrome133a",
    "chrome131",
    "chrome124",
    "chrome123",
    "chrome120",
    "chrome119",
    "chrome116",
    "chrome110",
    "chrome107",
    "chrome104",
    "chrome101",
    "chrome100",
    "chrome99",
)

_ACCEPT_LANGUAGE_POOL = (
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,en-GB;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.9,es-US;q=0.8",
    "en-CA,en;q=0.9,en-US;q=0.8",
)


def _chrome_major(impersonate: str) -> int:
    match = re.search(r"chrome(\d+)", impersonate)
    return int(match.group(1)) if match else 131


def _build_chrome_headers(major: int, chrome_version: str) -> Dict[str, str]:
    not_a_brand = "24" if major >= 116 else "99"
    return {
        "sec-ch-ua": (
            f'"Google Chrome";v="{major}", "Chromium";v="{major}", '
            f'"Not_A Brand";v="{not_a_brand}"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Safari/537.36"
        ),
        "accept": "application/json, text/plain, */*",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": random.choice(_ACCEPT_LANGUAGE_POOL),
        "priority": "u=1",
    }


def generate_run_fingerprint() -> dict:
    """每次进程启动随机一套 TLS + UA 指纹，与 impersonate 目标一致。"""
    impersonate = random.choice(_CHROME_DESKTOP_POOL)
    major = _chrome_major(impersonate)
    chrome_version = f"{major}.0.0.0"
    headers = _build_chrome_headers(major, chrome_version)
    return {
        "impersonate": impersonate,
        "headers": headers,
        "chrome_major": major,
        "chrome_version": chrome_version,
    }
