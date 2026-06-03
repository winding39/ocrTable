"""历史记录页 — 展示全部 OCR 操作结果。"""
from __future__ import annotations

import os
import subprocess
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils import history as history_store


def _open_file(path: str) -> None:
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


class HistoryPage(QWidget):
    COL_ID = 0
    COL_TIME = 1
    COL_PHOTOS = 2
    COL_XLSX = 3
    COL_STATUS = 4

    def __init__(self, main_window=None):
        super().__init__()
        self._main_window = main_window
        self._records: list[dict] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("历史记录")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("defaultButton")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        clear_btn = QPushButton("清空历史")
        clear_btn.setObjectName("dangerButton")
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)
        root.addLayout(header)

        hint = QLabel("双击 xlsx 列用 Excel 打开；双击照片列查看文件名列表")
        hint.setStyleSheet("color:#8C8C8C;font-size:12px;")
        root.addWidget(hint)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["序号", "时间", "照片", "xlsx 文件", "状态"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double_click)
        root.addWidget(self.table, stretch=1)

    def refresh(self):
        self._records = history_store.load_records()
        self.table.setRowCount(len(self._records))
        for row, rec in enumerate(self._records):
            rid = rec.get("id", row + 1)
            self.table.setItem(row, self.COL_ID, QTableWidgetItem(str(rid)))
            self.table.setItem(
                row, self.COL_TIME, QTableWidgetItem(rec.get("created_at", ""))
            )
            cnt = rec.get("photo_count", 0)
            names = rec.get("photo_names") or []
            photo_text = f"{cnt} 张"
            if names:
                photo_text += f"（{names[0]}" + (
                    f" 等" if len(names) > 1 else ""
                ) + "）"
            photo_item = QTableWidgetItem(photo_text)
            photo_item.setToolTip("\n".join(names))
            self.table.setItem(row, self.COL_PHOTOS, photo_item)

            xlsx_name = rec.get("xlsx_name") or os.path.basename(
                rec.get("xlsx_path", "") or ""
            )
            xlsx_item = QTableWidgetItem(xlsx_name or "-")
            xlsx_item.setToolTip(rec.get("xlsx_path", ""))
            self.table.setItem(row, self.COL_XLSX, xlsx_item)

            status = rec.get("status", "")
            status_item = QTableWidgetItem(status)
            if status == "success":
                status_item.setForeground(Qt.darkGreen)
            elif status == "failed":
                status_item.setForeground(Qt.red)
            msg = rec.get("message", "")
            if msg:
                status_item.setToolTip(msg)
            self.table.setItem(row, self.COL_STATUS, status_item)

        self.table.resizeColumnsToContents()

    def _record_at_row(self, row: int) -> dict | None:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def _on_cell_double_click(self, row: int, col: int):
        rec = self._record_at_row(row)
        if not rec:
            return
        if col == self.COL_XLSX:
            path = rec.get("xlsx_path", "")
            if not path:
                QMessageBox.information(self, "提示", "该记录无 xlsx 文件")
                return
            try:
                _open_file(path)
            except Exception as e:
                QMessageBox.warning(self, "打开失败", str(e))
        elif col == self.COL_PHOTOS:
            names = rec.get("photo_names") or []
            if not names:
                QMessageBox.information(self, "照片列表", "无照片记录")
                return
            QMessageBox.information(
                self,
                f"任务#{rec.get('task_id', rec.get('id', ''))} 照片",
                "\n".join(names),
            )

    def _clear_history(self):
        if (
            QMessageBox.question(
                self,
                "确认",
                "确定清空全部历史记录？",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        history_store.clear_records()
        self.refresh()
