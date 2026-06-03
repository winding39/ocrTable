"""拍照识别页 — 摄像头、照片列表、多任务 OCR、导出 xlsx。"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QTransform
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import config as cfg
from ocr.bailian import recognize_table
from utils import history as history_store
from utils.excel_export import export_results_to_xlsx

logger = logging.getLogger(__name__)

try:
    from PyQt5 import sip
except ImportError:
    sip = None  # type: ignore


def _qt_alive(obj) -> bool:
    if obj is None:
        return False
    if sip is None:
        return True
    try:
        return not sip.isdeleted(obj)
    except Exception:
        return False


def _default_preview_scale(pix: QPixmap) -> QPixmap:
    return pix.scaled(960, 720, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _unique_image_name(prefix: str, ext: str = ".jpg") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}{ext}"


def _open_file(path: str) -> None:
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


class PhotoViewerDialog(QDialog):
    """照片预览：放大、缩小、适应窗口、右转 90°。"""

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(image_path))
        self.resize(900, 700)
        self._image_path = image_path
        self._original = QPixmap(image_path)
        self._scale = 1.0
        self._rotate = 0
        self._fit_mode = True

        root = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setObjectName("viewerImage")
        self._scroll.setWidget(self._image_label)
        root.addWidget(self._scroll, stretch=1)

        bar = QHBoxLayout()
        zoom_in = QPushButton("放大 +")
        zoom_in.setObjectName("defaultButton")
        zoom_in.clicked.connect(lambda: self._zoom(0.2))
        bar.addWidget(zoom_in)

        zoom_out = QPushButton("缩小 -")
        zoom_out.setObjectName("defaultButton")
        zoom_out.clicked.connect(lambda: self._zoom(-0.2))
        bar.addWidget(zoom_out)

        fit_btn = QPushButton("适应窗口")
        fit_btn.setObjectName("defaultButton")
        fit_btn.clicked.connect(self._fit_window)
        bar.addWidget(fit_btn)

        rot_btn = QPushButton("右转 90°")
        rot_btn.setObjectName("defaultButton")
        rot_btn.clicked.connect(self._rotate_right)
        bar.addWidget(rot_btn)

        bar.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("primaryButton")
        close_btn.clicked.connect(self.accept)
        bar.addWidget(close_btn)
        root.addLayout(bar)

        self._fit_window()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom(0.15)
        elif delta < 0:
            self._zoom(-0.15)
        event.accept()

    def _zoom(self, step: float):
        self._fit_mode = False
        self._scale = max(0.1, min(5.0, self._scale + step))
        self._refresh()

    def _fit_window(self):
        self._fit_mode = True
        self._refresh()

    def _rotate_right(self):
        self._rotate = (self._rotate + 90) % 360
        self._refresh()

    def _refresh(self):
        if self._original.isNull():
            self._image_label.setText("无法加载图片")
            return
        pix = self._original.transformed(
            QTransform().rotate(self._rotate), Qt.SmoothTransformation
        )
        if self._fit_mode:
            vp = self._scroll.viewport().size()
            w, h = max(vp.width() - 20, 100), max(vp.height() - 20, 100)
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            w = max(1, int(pix.width() * self._scale))
            h = max(1, int(pix.height() * self._scale))
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._image_label.setPixmap(pix)
        self._image_label.resize(pix.size())


class OCRWorker(QObject):
    log_message = pyqtSignal(int, str)
    ocr_done = pyqtSignal(int, str, list)
    ocr_error = pyqtSignal(int, str, list)
    finished = pyqtSignal(int)

    def __init__(self, task_id: int, image_paths: list[str]):
        super().__init__()
        self.task_id = task_id
        self._paths = list(image_paths)

    def start_work(self) -> None:
        tid = self.task_id

        def run() -> None:
            photo_names = [os.path.basename(p) for p in self._paths]
            try:
                runtime = cfg.get_runtime_config()
                if not runtime.get("vision_api_key"):
                    self.ocr_error.emit(tid, "请先在【系统设定】中配置 API Key", photo_names)
                    return

                def log_cb(msg: str) -> None:
                    self.log_message.emit(tid, msg)

                results = []
                errors = []
                total = len(self._paths)
                self.log_message.emit(tid, f"开始批量识别，共 {total} 张照片")

                for i, path in enumerate(self._paths):
                    name = os.path.basename(path)
                    self.log_message.emit(
                        tid, f"========== [{i + 1}/{total}] {name} =========="
                    )
                    if not os.path.isfile(path):
                        msg = f"{name}: 文件不存在"
                        errors.append(msg)
                        self.log_message.emit(tid, msg)
                        continue
                    out = recognize_table(path, runtime=runtime, log_cb=log_cb)
                    if not out.get("success"):
                        msg = f"{name}: {out.get('error', '识别失败')}"
                        errors.append(msg)
                        self.log_message.emit(tid, f"失败: {msg}")
                        continue
                    data = out.get("data") or {}
                    results.append(
                        {
                            "filename": name,
                            "headers": data.get("headers") or [],
                            "rows": data.get("rows") or [],
                        }
                    )
                    self.log_message.emit(
                        tid,
                        f"✓ {name}：{len(data.get('headers', []))} 列，"
                        f"{len(data.get('rows', []))} 行",
                    )

                if not results:
                    err = "全部识别失败" + (
                        f"：{'; '.join(errors)}" if errors else ""
                    )
                    self.ocr_error.emit(tid, err, photo_names)
                    return

                self.log_message.emit(tid, "正在生成 xlsx...")
                xlsx_path = export_results_to_xlsx(results)
                self.log_message.emit(
                    tid, f"xlsx 已生成: {os.path.basename(xlsx_path)}"
                )
                if errors:
                    self.log_message.emit(tid, "部分失败: " + "; ".join(errors))
                self.ocr_done.emit(tid, xlsx_path, photo_names)
            except Exception as e:
                logger.exception("OCR 批量任务失败")
                self.ocr_error.emit(tid, str(e), photo_names)
            finally:
                self.finished.emit(tid)

        threading.Thread(
            target=run, daemon=True, name=f"ocr-batch-{tid}"
        ).start()


class CameraWorker(QThread):
    frame_ready = pyqtSignal(QImage)
    error = pyqtSignal(str)

    def __init__(self, cap, keep_cap: bool = False):
        super().__init__()
        self._cap = cap
        self._keep_cap = keep_cap
        self._running = False

    def run(self):
        try:
            from utils.camera import bgr_frame_to_qimage_copy, frame_ok

            self._running = True
            bad_frames = 0
            while self._running:
                try:
                    ret, frame = self._cap.read()
                except Exception as e:
                    bad_frames += 1
                    if bad_frames >= 30:
                        self.error.emit(f"摄像头读帧失败：{e}")
                        break
                    self.msleep(50)
                    continue
                if ret and frame_ok(frame):
                    try:
                        self.frame_ready.emit(bgr_frame_to_qimage_copy(frame))
                        bad_frames = 0
                    except Exception as e:
                        bad_frames += 1
                        if bad_frames >= 30:
                            self.error.emit(str(e))
                            break
                else:
                    bad_frames += 1
                    if bad_frames >= 30:
                        self.error.emit("摄像头无法输出有效画面")
                        break
                self.msleep(33)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if not self._keep_cap:
                try:
                    self._cap.release()
                except Exception:
                    pass

    def stop(self, keep_cap: bool = False):
        self._keep_cap = keep_cap
        self._running = False
        self.wait(3000)
        return self._cap if keep_cap else None


class _CameraOpenHelper(QObject):
    open_done = pyqtSignal(object, int, int)
    open_failed = pyqtSignal(str)

    def start_open(self, index: int, preferred_w: int, preferred_h: int) -> None:
        def run() -> None:
            try:
                from utils.camera import open_prepared_capture

                cap, w, h = open_prepared_capture(index, preferred_w, preferred_h)
                if cap is None or w <= 0:
                    self.open_failed.emit("无法打开摄像头，请检查设备连接")
                else:
                    self.open_done.emit(cap, w, h)
            except Exception as e:
                self.open_failed.emit(str(e))

        threading.Thread(target=run, daemon=True, name="camera-open").start()


class CapturePage(QWidget):
    ocr_completed = pyqtSignal(str)

    def __init__(self, main_window=None):
        super().__init__()
        self._main_window = main_window
        self._photo_paths: list[str] = []
        self._camera_worker: CameraWorker | None = None
        self._camera_active = False
        self._camera_open_busy = False
        self._cached_cap = None
        self._last_camera_image: QImage | None = None
        self._camera_helper: _CameraOpenHelper | None = None
        self._ocr_workers: list[OCRWorker] = []
        self._task_counter = 0
        self._task_status: dict[int, str] = {}
        self._xlsx_paths: list[str] = []
        self._camera_index = int(os.environ.get("CAMERA_INDEX", "0"))
        self._capture_w = int(os.environ.get("CAPTURE_WIDTH", "1920"))
        self._capture_h = int(os.environ.get("CAPTURE_HEIGHT", "1080"))
        self._jpeg_quality = int(os.environ.get("CAPTURE_JPEG_QUALITY", "95"))
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("拍照识别")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self.task_status_label = QLabel("")
        self.task_status_label.setStyleSheet("color:#1677FF;font-size:12px;")
        header.addWidget(self.task_status_label)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_image_panel(), stretch=3)
        body.addWidget(self._build_control_panel(), stretch=2)
        root.addLayout(body, stretch=1)

    def _build_image_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.image_label = QLabel("点击「打开摄像头」开始预览")
        self.image_label.setObjectName("previewLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(360)
        layout.addWidget(self.image_label, stretch=1)

        row = QHBoxLayout()
        self.open_cam_btn = QPushButton("打开摄像头")
        self.open_cam_btn.setObjectName("primaryButton")
        self.open_cam_btn.clicked.connect(self._start_camera)
        row.addWidget(self.open_cam_btn)

        self.capture_btn = QPushButton("拍照")
        self.capture_btn.setObjectName("defaultButton")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._capture_photo)
        row.addWidget(self.capture_btn)

        self.close_cam_btn = QPushButton("关闭摄像头")
        self.close_cam_btn.setObjectName("defaultButton")
        self.close_cam_btn.setEnabled(False)
        self.close_cam_btn.clicked.connect(self._stop_camera)
        row.addWidget(self.close_cam_btn)

        self.import_btn = QPushButton("选择照片")
        self.import_btn.setObjectName("defaultButton")
        self.import_btn.clicked.connect(self._import_images)
        row.addWidget(self.import_btn)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _build_control_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(440)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        layout.addWidget(QLabel("照片列表（双击预览）"))
        self.photo_list = QListWidget()
        self.photo_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.photo_list.itemDoubleClicked.connect(self._preview_photo)
        layout.addWidget(self.photo_list, stretch=2)

        del_row = QHBoxLayout()
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.clicked.connect(self._delete_selected)
        del_row.addWidget(self.delete_btn)

        self.delete_all_btn = QPushButton("删除全部")
        self.delete_all_btn.setObjectName("dangerButton")
        self.delete_all_btn.clicked.connect(self._delete_all)
        del_row.addWidget(self.delete_all_btn)
        del_row.addStretch()
        layout.addLayout(del_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#595959;font-size:12px;")
        layout.addWidget(self.status_label)

        self.ocr_btn = QPushButton("开始 OCR 识别")
        self.ocr_btn.setObjectName("primaryButton")
        self.ocr_btn.clicked.connect(self._start_ocr)
        layout.addWidget(self.ocr_btn)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("ocrLog")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(120)
        self.log_edit.setPlaceholderText("识别日志...")
        layout.addWidget(self.log_edit)

        layout.addWidget(QLabel("识别结果（双击用 Excel 打开）"))
        self.xlsx_list = QListWidget()
        self.xlsx_list.itemDoubleClicked.connect(self._open_xlsx_item)
        layout.addWidget(self.xlsx_list, stretch=1)

        xlsx_row = QHBoxLayout()
        self.open_xlsx_btn = QPushButton("打开选中")
        self.open_xlsx_btn.setObjectName("defaultButton")
        self.open_xlsx_btn.clicked.connect(self._open_selected_xlsx)
        xlsx_row.addWidget(self.open_xlsx_btn)

        self.download_btn = QPushButton("另存为...")
        self.download_btn.setObjectName("successButton")
        self.download_btn.clicked.connect(self._save_xlsx_as)
        xlsx_row.addWidget(self.download_btn)
        xlsx_row.addStretch()
        layout.addLayout(xlsx_row)

        self._load_existing_xlsx()
        return card

    def refresh(self):
        self._load_existing_xlsx()

    def _load_existing_xlsx(self):
        """加载 exports 目录已有 xlsx 到结果列表。"""
        self.xlsx_list.clear()
        self._xlsx_paths.clear()
        if not os.path.isdir(cfg.EXPORTS_DIR):
            return
        files = sorted(
            [
                f
                for f in os.listdir(cfg.EXPORTS_DIR)
                if f.lower().endswith(".xlsx")
            ],
            reverse=True,
        )
        for name in files:
            path = os.path.join(cfg.EXPORTS_DIR, name)
            if os.path.isfile(path):
                self._add_xlsx_to_list(path)

    def _add_xlsx_to_list(self, path: str):
        path = os.path.abspath(path)
        if path in self._xlsx_paths:
            return
        self._xlsx_paths.append(path)
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self.xlsx_list.insertItem(0, item)

    def _append_log(self, msg: str, task_id: int | None = None):
        if not _qt_alive(self.log_edit):
            return
        prefix = f"[任务#{task_id}] " if task_id is not None else ""
        self.log_edit.appendPlainText(prefix + msg)

    def _update_status(self, text: str):
        if _qt_alive(self.status_label):
            self.status_label.setText(text)

    def _update_task_status_bar(self):
        if not self._task_status:
            self.task_status_label.setText("")
            return
        parts = [
            f"任务#{tid} {st}" for tid, st in sorted(self._task_status.items())
        ]
        self.task_status_label.setText(" | ".join(parts))

    def _refresh_photo_list(self):
        self.photo_list.clear()
        for path in self._photo_paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.photo_list.addItem(item)
        self.ocr_btn.setEnabled(len(self._photo_paths) > 0)

    def _add_photo_path(self, path: str):
        if path not in self._photo_paths:
            self._photo_paths.append(path)
            self._refresh_photo_list()

    def _preview_photo(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "预览", "图片文件不存在")
            return
        dlg = PhotoViewerDialog(path, self)
        dlg.exec_()

    def _start_camera(self):
        if self._camera_open_busy or self._camera_active:
            return
        self._camera_open_busy = True
        self.open_cam_btn.setEnabled(False)
        self._update_status("正在打开摄像头...")

        if self._cached_cap is not None:
            from utils.camera import quick_warmup

            if quick_warmup(self._cached_cap):
                self._activate_camera(self._cached_cap, self._capture_w, self._capture_h)
                self._camera_open_busy = False
                return
            try:
                self._cached_cap.release()
            except Exception:
                pass
            self._cached_cap = None

        helper = _CameraOpenHelper()
        self._camera_helper = helper
        helper.open_done.connect(self._on_camera_open_done, Qt.QueuedConnection)
        helper.open_failed.connect(self._on_camera_open_failed, Qt.QueuedConnection)
        helper.start_open(self._camera_index, self._capture_w, self._capture_h)

    def _on_camera_open_done(self, cap, w, h):
        self._camera_open_busy = False
        if not _qt_alive(self):
            return
        self._cached_cap = cap
        self._activate_camera(cap, w, h)
        self._update_status(f"摄像头已打开 ({w}×{h})")

    def _on_camera_open_failed(self, msg: str):
        self._camera_open_busy = False
        if not _qt_alive(self):
            return
        self.open_cam_btn.setEnabled(True)
        self._update_status("")
        QMessageBox.warning(self, "摄像头", msg or "无法打开摄像头")

    def _activate_camera(self, cap, w, h):
        self._stop_camera_worker_only()
        self._camera_worker = CameraWorker(cap)
        self._camera_worker.frame_ready.connect(self._update_frame)
        self._camera_worker.error.connect(self._on_camera_error)
        self._camera_worker.start()
        self._camera_active = True
        self.open_cam_btn.setEnabled(False)
        self.capture_btn.setEnabled(True)
        self.close_cam_btn.setEnabled(True)

    def _update_frame(self, image: QImage):
        if not _qt_alive(self.image_label):
            return
        self._last_camera_image = image.copy()
        pix = QPixmap.fromImage(image)
        self.image_label.setPixmap(_default_preview_scale(pix))
        self.image_label.setStyleSheet(
            "background:#000;border:2px solid #1677FF;border-radius:6px;"
        )

    def _on_camera_error(self, msg: str):
        QMessageBox.warning(self, "摄像头", msg)
        self._stop_camera(keep_cap=False)

    def _stop_camera_worker_only(self):
        if self._camera_worker:
            self._cached_cap = self._camera_worker.stop(keep_cap=True)
            self._camera_worker = None
        self._camera_active = False

    def _stop_camera(self, keep_cap: bool = True):
        if self._camera_worker:
            cap = self._camera_worker.stop(keep_cap=keep_cap)
            if keep_cap:
                self._cached_cap = cap
            self._camera_worker = None
        elif self._cached_cap and not keep_cap:
            try:
                self._cached_cap.release()
            except Exception:
                pass
            self._cached_cap = None
        self._camera_active = False
        self.open_cam_btn.setEnabled(True)
        self.capture_btn.setEnabled(False)
        self.close_cam_btn.setEnabled(False)
        self.image_label.clear()
        self.image_label.setText("点击「打开摄像头」开始预览")
        self.image_label.setStyleSheet("")
        self._update_status("")

    def _capture_photo(self):
        if self._last_camera_image is None or self._last_camera_image.isNull():
            QMessageBox.warning(self, "拍照", "暂无画面，请等待摄像头就绪")
            return
        os.makedirs(cfg.IMAGES_DIR, exist_ok=True)
        name = _unique_image_name("capture", ".jpg")
        path = os.path.join(cfg.IMAGES_DIR, name)
        if not self._last_camera_image.save(path, "JPEG", self._jpeg_quality):
            QMessageBox.warning(self, "拍照", "保存照片失败")
            return
        self._add_photo_path(path)
        self._update_status(f"已拍照: {name}")
        pix = QPixmap.fromImage(self._last_camera_image)
        self.image_label.setPixmap(_default_preview_scale(pix))

    def _import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择照片",
            "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)",
        )
        if not paths:
            return
        os.makedirs(cfg.IMAGES_DIR, exist_ok=True)
        added = 0
        for src in paths:
            ext = os.path.splitext(src)[1].lower() or ".jpg"
            dest = os.path.join(cfg.IMAGES_DIR, _unique_image_name("import", ext))
            try:
                shutil.copy2(src, dest)
                self._add_photo_path(dest)
                added += 1
            except Exception as e:
                logger.warning("导入失败 %s: %s", src, e)
        self._update_status(f"已添加 {added} 张照片")

    def _delete_selected(self):
        rows = sorted(
            {self.photo_list.row(item) for item in self.photo_list.selectedItems()},
            reverse=True,
        )
        if not rows:
            return
        for row in rows:
            item = self.photo_list.item(row)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            if path in self._photo_paths:
                self._photo_paths.remove(path)
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        self._refresh_photo_list()
        self._update_status("已删除选中照片")

    def _delete_all(self):
        if not self._photo_paths:
            return
        n = len(self._photo_paths)
        if (
            QMessageBox.question(
                self,
                "确认",
                f"确定删除全部 {n} 张照片？",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        for path in list(self._photo_paths):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        self._photo_paths.clear()
        self._refresh_photo_list()
        self._update_status("已删除全部照片")

    def _start_ocr(self):
        if not self._photo_paths:
            QMessageBox.information(self, "提示", "请先拍照或选择照片")
            return

        paths_snapshot = list(self._photo_paths)
        photo_names = [os.path.basename(p) for p in paths_snapshot]

        self._photo_paths.clear()
        self._refresh_photo_list()

        self._task_counter += 1
        task_id = self._task_counter
        self._task_status[task_id] = "识别中"
        self._update_task_status_bar()

        self._append_log(f"=== 任务#{task_id} 开始，共 {len(paths_snapshot)} 张 ===")
        self._update_status(f"任务#{task_id} 识别中，可继续添加照片")

        worker = OCRWorker(task_id, paths_snapshot)
        self._ocr_workers.append(worker)
        worker.log_message.connect(self._on_worker_log, Qt.QueuedConnection)
        worker.ocr_done.connect(
            lambda tid, path, names, w=worker: self._on_ocr_done(w, path, names),
            Qt.QueuedConnection,
        )
        worker.ocr_error.connect(
            lambda tid, err, names, w=worker: self._on_ocr_error(w, err, names),
            Qt.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, w=worker: self._on_ocr_worker_finished(w, tid),
            Qt.QueuedConnection,
        )
        worker.start_work()

    def _on_worker_log(self, task_id: int, msg: str):
        self._append_log(msg, task_id)

    def _on_ocr_done(self, worker: OCRWorker, xlsx_path: str, photo_names: list):
        tid = worker.task_id
        self._task_status[tid] = "完成"
        self._update_task_status_bar()
        self._add_xlsx_to_list(xlsx_path)
        name = os.path.basename(xlsx_path)
        msg = f"任务#{tid} 识别完成：{name}"
        self._update_status(msg)
        self._append_log("========== " + msg + " ==========", tid)
        history_store.append_record(
            {
                "task_id": tid,
                "photo_count": len(photo_names),
                "photo_names": photo_names,
                "xlsx_path": xlsx_path,
                "status": "success",
                "message": msg,
            }
        )
        self.ocr_completed.emit(msg)

    def _on_ocr_error(self, worker: OCRWorker, err: str, photo_names: list):
        tid = worker.task_id
        self._task_status[tid] = "失败"
        self._update_task_status_bar()
        self._append_log("错误: " + err, tid)
        self._update_status(f"任务#{tid} 识别失败")
        history_store.append_record(
            {
                "task_id": tid,
                "photo_count": len(photo_names),
                "photo_names": photo_names,
                "status": "failed",
                "message": err,
            }
        )
        QMessageBox.critical(self, f"任务#{tid} 失败", err)

    def _on_ocr_worker_finished(self, worker: OCRWorker, task_id: int):
        if worker in self._ocr_workers:
            self._ocr_workers.remove(worker)
        worker.deleteLater()
        if task_id in self._task_status and self._task_status[task_id] == "识别中":
            self._task_status[task_id] = "结束"
        self._update_task_status_bar()

    def _selected_xlsx_path(self) -> str:
        item = self.xlsx_list.currentItem()
        if item:
            return item.data(Qt.UserRole) or ""
        if self.xlsx_list.count() > 0:
            return self.xlsx_list.item(0).data(Qt.UserRole) or ""
        return ""

    def _open_xlsx_item(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path:
            return
        try:
            _open_file(path)
        except Exception as e:
            QMessageBox.warning(self, "打开文件", str(e))

    def _open_selected_xlsx(self):
        path = self._selected_xlsx_path()
        if not path:
            QMessageBox.information(self, "提示", "请先选择或生成 xlsx 文件")
            return
        try:
            _open_file(path)
        except Exception as e:
            QMessageBox.warning(self, "打开文件", str(e))

    def _save_xlsx_as(self):
        path = self._selected_xlsx_path()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "另存为", "请先选择有效的 xlsx 文件")
            return
        default_name = os.path.basename(path)
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "另存为",
            default_name,
            "Excel 文件 (*.xlsx)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".xlsx"):
            dest += ".xlsx"
        try:
            shutil.copy2(path, dest)
            QMessageBox.information(self, "保存成功", f"已保存到:\n{dest}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def closeEvent(self, event):
        self._stop_camera(keep_cap=False)
        super().closeEvent(event)
