"""主窗口 — 侧边栏 + 页面栈。"""
from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ui.styles import MAIN_STYLE

logger = logging.getLogger(__name__)

NAV_ITEMS = [
    ("capture", "📷  拍照识别"),
    ("settings", "⚙  系统设定"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OCR 表格识别")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)
        self.setStyleSheet(MAIN_STYLE)
        self._pages: dict = {}
        self._nav_buttons: dict = {}
        self._current_page = ""
        self._build_ui()
        self._switch_page("capture")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content())
        status = QStatusBar()
        status.showMessage("  OCR 表格识别系统")
        self.setStatusBar(status)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)

        logo = QWidget()
        logo.setStyleSheet("background: #002040;")
        ll = QVBoxLayout(logo)
        ll.addWidget(QLabel("📊", alignment=Qt.AlignCenter))
        t = QLabel("OCR 表格")
        t.setObjectName("appTitle")
        t.setAlignment(Qt.AlignCenter)
        ll.addWidget(t)
        s = QLabel("拍照 · 识别 · 导出")
        s.setObjectName("appSubtitle")
        s.setAlignment(Qt.AlignCenter)
        ll.addWidget(s)
        layout.addWidget(logo)
        layout.addSpacing(8)

        for pid, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, p=pid: self._switch_page(p))
            layout.addWidget(btn)
            self._nav_buttons[pid] = btn

        layout.addStretch()
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("contentArea")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        return content

    def _switch_page(self, page_id: str):
        if self._current_page == page_id:
            return
        for pid, btn in self._nav_buttons.items():
            btn.setProperty("active", "true" if pid == page_id else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if page_id not in self._pages:
            page = self._create_page(page_id)
            if page:
                self._pages[page_id] = page
                self.stack.addWidget(page)

        page = self._pages.get(page_id)
        if page:
            self.stack.setCurrentWidget(page)
            self._current_page = page_id
            if hasattr(page, "refresh"):
                page.refresh()

    def _create_page(self, page_id: str):
        if page_id == "capture":
            from ui.pages.capture_page import CapturePage

            page = CapturePage(main_window=self)
            page.ocr_completed.connect(self._on_ocr_completed)
            return page
        if page_id == "settings":
            from ui.pages.settings_page import SettingsPage

            return SettingsPage(main_window=self)
        return None

    def _on_ocr_completed(self, message: str):
        sb = self.statusBar()
        if sb:
            sb.showMessage(f"  {message}", 10000)
        logger.info(message)
