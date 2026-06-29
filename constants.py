import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DATA_DIR = os.path.join(PACKAGE_DIR, "app_data")

CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")

DEFAULT_PROXY_PORT = 7897
TOKEN_TTL_SECONDS = 600
TOKEN_REFRESH_MARGIN = 60

# GitHub 更新源（zip 分发同事自动 --update）；环境变量 APPSTORE_MONITOR_UPDATE_REPO 可覆盖
DEFAULT_UPDATE_REPO = "ZSYLOVE/appstore_review_monitor"

# 新应用默认随机轮询区间（秒）；可在添加时手动覆盖
CHECK_INTERVAL_RANDOM_MIN = 300
CHECK_INTERVAL_RANDOM_MAX = 720

# 静态兜底；正常运行时由 fingerprint.generate_run_fingerprint() 每次启动随机覆盖
DEFAULT_IMPERSONATE_TARGET = "chrome131"

APP_STORE_STATES = {
    "READY_FOR_SALE":                   "🟢 已上架 (Ready for Sale) - 恭喜！审核已通过并上架！",
    "PREPARE_FOR_SUBMISSION":           "📝 准备提交 (Prepare for Submission)",
    "WAITING_FOR_REVIEW":               "⏳ 等待审核 (Waiting for Review)",
    "IN_REVIEW":                        "🔍 正在审核 (In Review)",
    "PENDING_CONTRACT":                 "⚠️ 协议待处理 (Pending Contract) - 需签署付费/免费协议",
    "WAITING_FOR_EXPORT_COMPLIANCE":    "⚠️ 等待出口合规 (Waiting for Export Compliance)",
    "PENDING_DEVELOPER_RELEASE":        "🟡 待开发者发布 (Pending Developer Release) - 审核已通过",
    "PROCESSING_FOR_APP_STORE":         "⚙️ 处理中 (Processing for App Store)",
    "PENDING_APPLE_RELEASE":            "⏳ 等待苹果发布 (Pending Apple Release)",
    "REJECTED":                         "🔴 被拒绝 (Rejected) - 很遗憾,App 被拒了，请查看被拒邮件。",
    "DEVELOPER_REJECTED":               "🔴 开发者撤回 (Developer Rejected)",
    "REMOVED_FROM_SALE":                "❌ 已下架 (Removed from Sale)",
    "DEVELOPER_REMOVED_FROM_SALE":      "❌ 开发者已下架 (Developer Removed from Sale)",
    "INVALID_BINARY":                   "🚫 无效二进制 (Invalid Binary) - 需重新上传构建版本",
    "METADATA_REJECTED":                "🔴 元数据被拒 (Metadata Rejected) - 截图/描述等需修改",
    "PREORDER_READY_FOR_SALE":          "🟢 预购就绪 (Preorder Ready for Sale)",
    "REPLACED_WITH_NEW_VERSION":        "♻️ 已被新版本替换 (Replaced with New Version)",
    "ACCEPTED":                         "✅ 已接受 (Accepted)",
    "READY_FOR_REVIEW":                 "📤 准备审核 (Ready for Review) - 可提交审核",
    "NOT_APPLICABLE":                   "➖ 不适用 (Not Applicable)",
}

APPROVED_STATES = ["READY_FOR_SALE", "PENDING_DEVELOPER_RELEASE", "PREORDER_READY_FOR_SALE", "ACCEPTED"]
REJECTED_STATES = ["REJECTED", "METADATA_REJECTED", "DEVELOPER_REJECTED", "INVALID_BINARY"]
DELISTED_STATES = ["REMOVED_FROM_SALE", "DEVELOPER_REMOVED_FROM_SALE"]

# 不含 sec-fetch-site：该字段随请求场景在 apple_headers() 中设置（same-site）
CHROME_BASE_HEADERS = {
    "sec-ch-ua":                 '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile":          "?0",
    "sec-ch-ua-platform":        '"macOS"',
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "accept":                    "application/json, text/plain, */*",
    "sec-fetch-mode":            "cors",
    "sec-fetch-dest":            "empty",
    "accept-encoding":           "gzip, deflate, br, zstd",
    "accept-language":           "en-US,en;q=0.9",
    "priority":                  "u=1",
}

FILE_MODE_PRIVATE = 0o600
DIR_MODE_PRIVATE = 0o700
