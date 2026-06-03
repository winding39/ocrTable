"""拍照识别页 — 摄像头、照片列表、批量 OCR、导出 xlsx。"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import uuid
from datetime import datetime

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config as cfg
from ocr.bailian import recognize_table
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


class OCRWorker(QObject):
    log_message = pyqtSignal(str)
    ocr_done = pyqtSignal(str)
    ocr_error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, image_paths: list[str]):
        super().__init__()
        self._paths = list(image_paths)

    def start_work(self) -> None:
        def run() -> None:
            try:
                runtime = cfg.get_runtime_config()
                if not runtime.get("vision_api_key"):
                    self.ocr_error.emit("请先在【系统设定】中配置 API Key")
                    return

                def log_cb(msg: str) -> None:
                    self.log_message.emit(msg)

                results = []
                errors = []
                total = len(self._paths)
                self.log_message.emit(f"开始批量识别，共 {total} 张照片")

                for i, path in enumerate(self._paths):
                    name = os.path.basename(path)
                    self.log_message.emit(f"========== [{i + 1}/{total}] {name} ==========")
                    if not os.path.isfile(path):
                        msg = f"{name}: 文件不存在"
                        errors.append(msg)
                        self.log_message.emit(msg)
                        continue
                    out = recognize_table(path, runtime=runtime, log_cb=log_cb)
                    if not out.get("success"):
                        msg = f"{name}: {out.get('error', '识别失败')}"
                        errors.append(msg)
                        self.log_message.emit(f"失败: {msg}")
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
                        f"✓ {name}：{len(data.get('headers', []))} 列，"
                        f"{len(data.get('rows', []))} 行"
                    )

                if not results:
                    self.ocr_error.emit(
                        "全部识别失败"
                        + (f"：{'; '.join(errors)}" if errors else "")
                    )
                    return

                self.log_message.emit("正在生成 xlsx...")
                xlsx_path = export_results_to_xlsx(results)
                self.log_message.emit(f"xlsx 已生成: {os.path.basename(xlsx_path)}")
                if errors:
                    self.log_message.emit("部分失败: " + "; ".join(errors))
                self.ocr_done.emit(xlsx_path)
            except Exception as e:
                logger.exception("OCR 批量任务失败")
                self.ocr_error.emit(str(e))
            finally:
                self.finished.emit()

        threading.Thread(target=run, daemon=True, name="ocr-batch").start()


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
        self._ocr_worker: OCRWorker | None = None
        self._xlsx_path: str = ""
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
        card.setMaximumWidth(420)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("照片列表（文件名）"))
        self.photo_list = QListWidget()
        self.photo_list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.photo_list, stretch=1)

        del_row = QHBoxLayout()
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.clicked.connect(self._delete_selected)
        del_row.addWidget(self.delete_btn)
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
        self.log_edit.setMaximumHeight(160)
        self.log_edit.setPlaceholderText("识别日志将显示在这里...")
        layout.addWidget(self.log_edit)

        self.download_btn = QPushButton("另存为 xlsx...")
        self.download_btn.setObjectName("successButton")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._save_xlsx_as)
        layout.addWidget(self.download_btn)
        return card

    def refresh(self):
        pass

    def _append_log(self, msg: str):
        if not _qt_alive(self.log_edit):
            return
        self.log_edit.appendPlainText(msg)

    def _update_status(self, text: str):
        if _qt_alive(self.status_label):
            self.status_label.setText(text)

    def _refresh_photo_list(self):
        self.photo_list.clear()
        for path in self._photo_paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            self.photo_list.addItem(item)
        self.ocr_btn.setEnabled(len(self._photo_paths) > 0)

    def _add_photo_path(self, path: str):
        if path not in self._photo_paths:
            self._photo_paths.append(path)
            self._refresh_photo_list()

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

    def _start_ocr(self):
        if not self._photo_paths:
            QMessageBox.information(self, "提示", "请先拍照或选择照片")
            return
        if self._ocr_worker is not None:
            QMessageBox.information(self, "提示", "识别任务进行中，请稍候")
            return

        self.log_edit.clear()
        self.download_btn.setEnabled(False)
        self._xlsx_path = ""
        self.ocr_btn.setEnabled(False)
        self._update_status("正在识别...")
        self._append_log("开始 OCR 任务...")

        worker = OCRWorker(list(self._photo_paths))
        self._ocr_worker = worker
        worker.log_message.connect(self._append_log, Qt.QueuedConnection)
        worker.ocr_done.connect(self._on_ocr_done, Qt.QueuedConnection)
        worker.ocr_error.connect(self._on_ocr_error, Qt.QueuedConnection)
        worker.finished.connect(
            lambda w=worker: self._on_ocr_worker_finished(w), Qt.QueuedConnection
        )
        worker.start_work()

    def _on_ocr_done(self, xlsx_path: str):
        self._xlsx_path = xlsx_path
        self.download_btn.setEnabled(True)
        name = os.path.basename(xlsx_path)
        msg = f"识别完成！可另存为 xlsx（{name}）"
        self._update_status(msg)
        self._append_log("========== " + msg + " ==========")
        QMessageBox.information(self, "识别完成", msg)
        self.ocr_completed.emit(msg)

    def _on_ocr_error(self, msg: str):
        self._update_status("识别失败")
        self._append_log("错误: " + msg)
        QMessageBox.critical(self, "识别失败", msg)

    def _on_ocr_worker_finished(self, worker: OCRWorker):
        if self._ocr_worker is worker:
            self._ocr_worker = None
        worker.deleteLater()
        self.ocr_btn.setEnabled(len(self._photo_paths) > 0)

    def _save_xlsx_as(self):
        if not self._xlsx_path or not os.path.isfile(self._xlsx_path):
            QMessageBox.warning(self, "下载", "xlsx 文件不存在，请重新识别")
            return
        default_name = os.path.basename(self._xlsx_path)
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
            shutil.copy2(self._xlsx_path, dest)
            QMessageBox.information(self, "保存成功", f"已保存到:\n{dest}")
            self._update_status(f"已保存: {os.path.basename(dest)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def closeEvent(self, event):
        self._stop_camera(keep_cap=False)
        if self._ocr_worker:
            pass
        super().closeEvent(event)
