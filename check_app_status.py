import os
import sys
import warnings

warnings.simplefilter("ignore")

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_pkg_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import atexit

from appstore_review_monitor.deps import check_and_install_dependencies

check_and_install_dependencies()

from appstore_review_monitor.auth import clear_secret_caches  # noqa: E402
from appstore_review_monitor.cli import main  # noqa: E402

atexit.register(clear_secret_caches)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        clear_secret_caches()
        print("\n\n⏹️ 监控已手动停止。再见！")
