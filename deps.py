import os
import sys
import subprocess


def _has_pyjwt() -> bool:
    try:
        import jwt
    except ImportError:
        return False
    return callable(getattr(jwt, "encode", None))


def _has_package(import_name: str) -> bool:
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False


def _collect_missing_packages() -> list:
    missing = []
    if not _has_pyjwt():
        missing.append("PyJWT")
    if not _has_package("cryptography"):
        missing.append("cryptography")
    if not _has_package("curl_cffi"):
        missing.append("curl_cffi")
    if not _has_package("socks"):
        missing.append("PySocks")
    if not _has_package("psutil"):
        missing.append("psutil")
    return missing


def _pip_install(packages: list) -> None:
    indexes = [
        ("https://pypi.tuna.tsinghua.edu.cn/simple", "pypi.tuna.tsinghua.edu.cn"),
        (None, None),
    ]
    last_error = None
    for index_url, trusted_host in indexes:
        cmd = [sys.executable, "-m", "pip", "install"]
        if index_url:
            cmd.extend(["-i", index_url, "--trusted-host", trusted_host])
        cmd.extend(packages)
        try:
            subprocess.check_call(cmd)
            return
        except subprocess.CalledProcessError as e:
            last_error = e
    raise last_error


def _fix_wrong_jwt_package() -> bool:
    """卸载错误的 jwt 包（非 PyJWT），避免 import jwt 成功但无 encode。"""
    try:
        import jwt
    except ImportError:
        return False
    if callable(getattr(jwt, "encode", None)):
        return False
    print("⚠️  检测到错误的 jwt 包（非 PyJWT），正在卸载…")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "uninstall", "-y", "jwt"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def check_and_install_dependencies() -> None:
    if _fix_wrong_jwt_package():
        if _has_pyjwt():
            return

    missing_packages = _collect_missing_packages()
    if not missing_packages:
        return

    opt_out = os.environ.get("APPSTORE_CHECK_AUTO_INSTALL", "").strip().lower() in (
        "0", "false", "no", "off"
    )
    install_hint = (
        f"{sys.executable} -m pip install "
        f"-i https://pypi.tuna.tsinghua.edu.cn/simple "
        f"--trusted-host pypi.tuna.tsinghua.edu.cn "
        f"{' '.join(missing_packages)}"
    )
    if opt_out:
        print(f"❌ 缺少依赖包: {', '.join(missing_packages)}")
        if "PyJWT" in missing_packages:
            print("   （JWT 请安装 PyJWT，不要安装名为 jwt 的错误包）")
        print(f"请手动安装:\n  {install_hint}")
        print("或取消环境变量 APPSTORE_CHECK_AUTO_INSTALL=0 以允许自动安装。")
        sys.exit(1)

    print(f"📦 正在自动安装缺失的依赖包: {', '.join(missing_packages)}...")
    try:
        _pip_install(missing_packages)
        print("✅ 依赖安装成功！\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except subprocess.CalledProcessError as e:
        print(f"❌ 自动安装依赖失败: {e}")
        print(f"请手动安装:\n  {install_hint}")
        sys.exit(1)
