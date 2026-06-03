"""OCR 表格识别 — PyQt5 桌面应用入口。"""
from __future__ import annotations

import logging
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

if getattr(sys, "frozen", False):
    _base = os.path.dirname(sys.executable)
else:
    _base = os.path.dirname(os.path.abspath(__file__))

_env_path = os.path.join(_base, ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

import config as cfg

cfg.VISION_API_URL = os.environ.get("VISION_API_URL", cfg.VISION_API_URL)
cfg.VISION_API_KEY = os.environ.get("VISION_API_KEY", cfg.VISION_API_KEY)
cfg.VISION_API_MODEL = os.environ.get("VISION_API_MODEL", cfg.VISION_API_MODEL)
_ocr_ts = os.environ.get("OCR_TWO_STAGE", "1").strip().lower()
cfg.OCR_TWO_STAGE = _ocr_ts not in ("0", "false", "no")

_log_file = os.path.join(cfg.LOGS_DIR, "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("OCR 表格识别")
    app.setOrganizationName("ocrTable")
    app.setFont(QFont("Microsoft YaHei", 9))

    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    logger.info("应用已启动")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
