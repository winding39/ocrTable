"""系统设定页 — 模型与提示词。"""
from __future__ import annotations

import logging

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config as cfg

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self._main_window = main_window
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel("系统设定")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_model_tab(), "模型设置")
        self.tabs.addTab(self._build_prompt_tab(), "提示词")
        inner_layout.addWidget(self.tabs)

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

    def _build_model_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self.url_edit = QLineEdit()
        form.addRow("API Base URL", self.url_edit)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("留空则不修改已保存的 Key")
        key_row.addWidget(self.key_edit)
        self.key_hint = QLabel("")
        self.key_hint.setStyleSheet("color:#8C8C8C;font-size:12px;")
        form.addRow("API Key", self.key_edit)
        form.addRow("", self.key_hint)

        self.vision_model_edit = QLineEdit()
        form.addRow("视觉模型", self.vision_model_edit)

        self.text_model_edit = QLineEdit()
        form.addRow("文本结构化模型", self.text_model_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("两阶段（视觉转写 → JSON 提取）", True)
        self.mode_combo.addItem("单阶段（一张图直接 JSON）", False)
        form.addRow("OCR 模式", self.mode_combo)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1024, 32768)
        self.max_tokens_spin.setSingleStep(1024)
        form.addRow("最大 Tokens", self.max_tokens_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 600)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("API 超时", self.timeout_spin)

        save_btn = QPushButton("保存模型设置")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_model)
        form.addRow("", save_btn)
        return w

    def _build_prompt_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g1 = QGroupBox("Stage 1 — 视觉转写")
        l1 = QVBoxLayout(g1)
        self.stage1_edit = QPlainTextEdit()
        self.stage1_edit.setMinimumHeight(100)
        l1.addWidget(self.stage1_edit)
        layout.addWidget(g1)

        g2 = QGroupBox("Stage 2 — 表格提取 JSON")
        l2 = QVBoxLayout(g2)
        self.stage2_edit = QPlainTextEdit()
        self.stage2_edit.setMinimumHeight(120)
        l2.addWidget(self.stage2_edit)
        layout.addWidget(g2)

        g3 = QGroupBox("单阶段提示词")
        l3 = QVBoxLayout(g3)
        self.single_edit = QPlainTextEdit()
        self.single_edit.setMinimumHeight(100)
        l3.addWidget(self.single_edit)
        layout.addWidget(g3)

        row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.setObjectName("defaultButton")
        reset_btn.clicked.connect(self._reset_prompts)
        row.addWidget(reset_btn)
        save_btn = QPushButton("保存提示词")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_prompts)
        row.addWidget(save_btn)
        row.addStretch()
        layout.addLayout(row)
        return w

    def refresh(self):
        pub = cfg.get_public_settings()
        self.url_edit.setText(pub.get("vision_api_url") or "")
        self.vision_model_edit.setText(pub.get("vision_api_model") or "")
        self.text_model_edit.setText(pub.get("text_structure_model") or "")
        self.max_tokens_spin.setValue(int(pub.get("ocr_max_tokens") or 16384))
        self.timeout_spin.setValue(int(pub.get("ocr_api_timeout") or 300))
        two_stage = pub.get("ocr_two_stage", True)
        self.mode_combo.setCurrentIndex(0 if two_stage else 1)
        if pub.get("vision_api_key_set"):
            masked = pub.get("vision_api_key_masked") or "****"
            self.key_hint.setText(f"已配置 Key: {masked}")
        else:
            self.key_hint.setText("尚未配置 API Key")

        self.stage1_edit.setPlainText(cfg.get_stage1_prompt())
        self.stage2_edit.setPlainText(cfg.get_stage2_prompt())
        self.single_edit.setPlainText(cfg.get_single_prompt())

    def _save_model(self):
        payload = {
            "vision_api_url": self.url_edit.text().strip(),
            "vision_api_model": self.vision_model_edit.text().strip(),
            "text_structure_model": self.text_model_edit.text().strip(),
            "ocr_two_stage": self.mode_combo.currentData(),
            "ocr_max_tokens": self.max_tokens_spin.value(),
            "ocr_api_timeout": self.timeout_spin.value(),
        }
        key = self.key_edit.text().strip()
        if key:
            payload["vision_api_key"] = key
        try:
            cfg.save_model_settings(payload)
            cfg.write_env_from_settings()
            self.key_edit.clear()
            self.refresh()
            QMessageBox.information(self, "保存成功", "模型设置已保存")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _reset_prompts(self):
        if QMessageBox.question(
            self, "确认", "确定恢复为默认提示词？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.stage1_edit.setPlainText(cfg.DEFAULT_STAGE1_PROMPT)
        self.stage2_edit.setPlainText(cfg.DEFAULT_STAGE2_PROMPT)
        self.single_edit.setPlainText(cfg.DEFAULT_SINGLE_PROMPT)

    def _save_prompts(self):
        try:
            cfg.save_prompt_settings({
                "stage1_prompt": self.stage1_edit.toPlainText(),
                "stage2_prompt": self.stage2_edit.toPlainText(),
                "single_prompt": self.single_edit.toPlainText(),
            })
            QMessageBox.information(self, "保存成功", "提示词已保存")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
