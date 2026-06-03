"""系统设定页 — 模型与提示词。"""
from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
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
        self._device_tab_index = self.tabs.addTab(self._build_device_tab(), "设备")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._device_probed = False
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

        self.vision_enable_thinking = QCheckBox(
            "启用深度思考（仅 qwen3 系列模型有效）"
        )
        form.addRow(self.vision_enable_thinking)

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

    _RESOLUTION_PRESETS = [
        (3200, 2400),
        (1920, 1080),
        (1280, 720),
        (640, 480),
    ]

    def _build_device_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)

        cam_group = QGroupBox("摄像头")
        cam_form = QFormLayout(cam_group)
        self.cam_combo = QComboBox()
        self.cam_combo.setMinimumWidth(280)
        cam_form.addRow("设备", self.cam_combo)
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("刷新设备列表")
        refresh_btn.setObjectName("defaultButton")
        refresh_btn.clicked.connect(self._refresh_cameras)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        cam_form.addRow("", btn_row)
        self.cam_hint = QLabel("进入本页或点击刷新将探测可用摄像头（需在主线程执行）")
        self.cam_hint.setStyleSheet("color:#8C8C8C;font-size:12px;")
        self.cam_hint.setWordWrap(True)
        cam_form.addRow("", self.cam_hint)
        layout.addWidget(cam_group)

        res_group = QGroupBox("采集分辨率")
        res_form = QFormLayout(res_group)
        self.res_preset_combo = QComboBox()
        for rw, rh in self._RESOLUTION_PRESETS:
            self.res_preset_combo.addItem(f"{rw} × {rh}", (rw, rh))
        self.res_preset_combo.currentIndexChanged.connect(self._on_res_preset_changed)
        res_form.addRow("常用预设", self.res_preset_combo)
        res_wh_row = QHBoxLayout()
        self.capture_width_spin = QSpinBox()
        self.capture_width_spin.setRange(640, 3840)
        self.capture_height_spin = QSpinBox()
        self.capture_height_spin.setRange(480, 2880)
        self.capture_width_spin.valueChanged.connect(self._on_capture_size_changed)
        self.capture_height_spin.valueChanged.connect(self._on_capture_size_changed)
        res_wh_row.addWidget(self.capture_width_spin)
        res_wh_row.addWidget(QLabel("×"))
        res_wh_row.addWidget(self.capture_height_spin)
        res_wh_row.addStretch()
        res_form.addRow("宽 × 高", res_wh_row)
        self.jpeg_quality_spin = QSpinBox()
        self.jpeg_quality_spin.setRange(1, 100)
        self.jpeg_quality_spin.setSuffix(" %")
        res_form.addRow("JPEG 质量", self.jpeg_quality_spin)
        self.res_hint = QLabel(
            "实际分辨率以摄像头支持为准，打开时会按预设及候选分辨率依次尝试。"
        )
        self.res_hint.setStyleSheet("color:#8C8C8C;font-size:12px;")
        self.res_hint.setWordWrap(True)
        res_form.addRow("", self.res_hint)
        layout.addWidget(res_group)

        save_btn = QPushButton("保存设备设置")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_device)
        layout.addWidget(save_btn)
        layout.addStretch()
        return w

    def _on_res_preset_changed(self, index: int):
        data = self.res_preset_combo.itemData(index)
        if not data:
            return
        w, h = data
        self.capture_width_spin.blockSignals(True)
        self.capture_height_spin.blockSignals(True)
        self.capture_width_spin.setValue(w)
        self.capture_height_spin.setValue(h)
        self.capture_width_spin.blockSignals(False)
        self.capture_height_spin.blockSignals(False)

    def _on_capture_size_changed(self, _value: int = 0):
        w = self.capture_width_spin.value()
        h = self.capture_height_spin.value()
        for i in range(self.res_preset_combo.count()):
            if self.res_preset_combo.itemData(i) == (w, h):
                self.res_preset_combo.blockSignals(True)
                self.res_preset_combo.setCurrentIndex(i)
                self.res_preset_combo.blockSignals(False)
                return
        self.res_preset_combo.blockSignals(True)
        self.res_preset_combo.setCurrentIndex(-1)
        self.res_preset_combo.blockSignals(False)

    def _sync_resolution_ui(self, width: int, height: int, quality: int):
        self.capture_width_spin.blockSignals(True)
        self.capture_height_spin.blockSignals(True)
        self.capture_width_spin.setValue(width)
        self.capture_height_spin.setValue(height)
        self.jpeg_quality_spin.setValue(quality)
        self.capture_width_spin.blockSignals(False)
        self.capture_height_spin.blockSignals(False)
        self._on_capture_size_changed()

    def showEvent(self, event):
        super().showEvent(event)
        if self.tabs.currentIndex() == self._device_tab_index:
            self._refresh_cameras(silent=True)

    def _on_tab_changed(self, index: int):
        if index == self._device_tab_index:
            self._refresh_cameras(silent=not self._device_probed)

    def _refresh_cameras(self, silent: bool = False):
        from utils.camera import probe_cameras

        saved_idx = cfg.get_camera_index()
        try:
            found = probe_cameras(max_index=4)
        except Exception as e:
            logger.exception("探测摄像头失败")
            if not silent:
                QMessageBox.warning(self, "探测失败", str(e))
            return

        self._device_probed = True
        self.cam_combo.clear()
        if not found:
            self.cam_combo.addItem(f"摄像头 {saved_idx}（未探测到设备，使用已保存索引）", saved_idx)
            if not silent:
                QMessageBox.information(
                    self,
                    "提示",
                    "未探测到可用摄像头，已保留上次保存的索引。\n"
                    "请确认设备已连接后再次刷新。",
                )
        else:
            for idx, label in found:
                self.cam_combo.addItem(label, idx)
            self._select_camera_index(saved_idx)

        self.cam_hint.setText(
            f"当前保存的摄像头索引: {saved_idx}"
            + (f"，已探测 {len(found)} 个设备" if found else "，未探测到设备")
        )

    def _select_camera_index(self, index: int) -> None:
        for i in range(self.cam_combo.count()):
            if self.cam_combo.itemData(i, Qt.UserRole) == index:
                self.cam_combo.setCurrentIndex(i)
                return
        if self.cam_combo.count() > 0:
            self.cam_combo.setCurrentIndex(0)

    def refresh(self):
        pub = cfg.get_public_settings()
        self.url_edit.setText(pub.get("vision_api_url") or "")
        self.vision_model_edit.setText(pub.get("vision_api_model") or "")
        self.text_model_edit.setText(pub.get("text_structure_model") or "")
        self.max_tokens_spin.setValue(int(pub.get("ocr_max_tokens") or 16384))
        self.timeout_spin.setValue(int(pub.get("ocr_api_timeout") or 300))
        two_stage = pub.get("ocr_two_stage", True)
        self.mode_combo.setCurrentIndex(0 if two_stage else 1)
        self.vision_enable_thinking.setChecked(
            bool(pub.get("vision_enable_thinking", False))
        )
        if pub.get("vision_api_key_set"):
            masked = pub.get("vision_api_key_masked") or "****"
            self.key_hint.setText(f"已配置 Key: {masked}")
        else:
            self.key_hint.setText("尚未配置 API Key")

        self.stage1_edit.setPlainText(cfg.get_stage1_prompt())
        self.stage2_edit.setPlainText(cfg.get_stage2_prompt())
        self.single_edit.setPlainText(cfg.get_single_prompt())

        self._sync_resolution_ui(
            int(pub.get("capture_width") or 1920),
            int(pub.get("capture_height") or 1080),
            int(pub.get("capture_jpeg_quality") or 95),
        )

    def _save_model(self):
        payload = {
            "vision_api_url": self.url_edit.text().strip(),
            "vision_api_model": self.vision_model_edit.text().strip(),
            "text_structure_model": self.text_model_edit.text().strip(),
            "ocr_two_stage": self.mode_combo.currentData(),
            "vision_enable_thinking": self.vision_enable_thinking.isChecked(),
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

    def _save_device(self):
        if self.cam_combo.count() == 0:
            QMessageBox.warning(self, "提示", "请先刷新设备列表")
            return
        idx = self.cam_combo.currentData(Qt.UserRole)
        if idx is None:
            QMessageBox.warning(self, "提示", "请选择摄像头")
            return
        try:
            cfg.save_device_settings({
                "camera_index": int(idx),
                "capture_width": self.capture_width_spin.value(),
                "capture_height": self.capture_height_spin.value(),
                "capture_jpeg_quality": self.jpeg_quality_spin.value(),
            })
            cfg.write_env_from_settings()
            self.refresh()
            self._refresh_cameras(silent=True)
            QMessageBox.information(
                self,
                "保存成功",
                f"摄像头 {idx}，分辨率 {self.capture_width_spin.value()}×"
                f"{self.capture_height_spin.value()}",
            )
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
