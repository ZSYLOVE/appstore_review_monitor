import warnings

warnings.simplefilter("ignore")

from .deps import check_and_install_dependencies

check_and_install_dependencies()

from .cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️ 监控已手动停止。再见！")
