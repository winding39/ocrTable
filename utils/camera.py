"""摄像头枚举与采集（Windows 优先 DirectShow，降低 MSMF 流损坏概率）。"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import List, Tuple

logger = logging.getLogger(__name__)

_RESOLUTION_PRESETS: List[Tuple[int, int]] = [
    (3200, 2400),
    (2400, 1800),
    (2560, 1440),
    (1920, 1080),
    (1600, 1200),
    (1280, 960),
    (1280, 1024),
    (1280, 720),
    (1024, 768),
    (640, 480),
]


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def open_video_capture(index: int):
    import cv2

    idx = int(index)
    if _is_windows():
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap
        try:
            cap.release()
        except Exception:
            pass
    return cv2.VideoCapture(idx)


def frame_ok(frame) -> bool:
    if frame is None:
        return False
    try:
        if not hasattr(frame, "shape") or len(frame.shape) < 2:
            return False
        h, w = int(frame.shape[0]), int(frame.shape[1])
        if h < 240 or w < 320:
            return False
        return h > 0 and w > 0 and int(getattr(frame, "size", 0)) > 0
    except Exception:
        return False


def _resolution_candidates(preferred_w: int, preferred_h: int) -> List[Tuple[int, int]]:
    presets: List[Tuple[int, int]] = [(int(preferred_w), int(preferred_h))]
    for p in _RESOLUTION_PRESETS:
        if p not in presets:
            presets.append(p)
    return presets


def bgr_frame_to_qimage_copy(frame):
    import cv2
    import numpy as np
    from PyQt5.QtGui import QImage

    if not frame_ok(frame):
        raise ValueError("invalid camera frame (empty or zero size)")

    if len(frame.shape) == 2:
        bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.shape[2] == 4:
        bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    elif frame.shape[2] == 3:
        bgr = np.ascontiguousarray(frame)
    else:
        raise ValueError(f"unsupported frame channels: {frame.shape}")

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    bytes_per_line = 3 * w
    qimg = QImage(rgb.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888)
    return qimg.copy()


def _warmup_read_valid_frame(cap, attempts: int = 15):
    for _ in range(5):
        try:
            cap.grab()
        except Exception:
            pass
    last_good = None
    for _ in range(max(1, attempts)):
        try:
            ret, frame = cap.read()
            if ret and frame_ok(frame):
                last_good = frame
        except Exception as e:
            logger.debug("读帧失败: %s", e)
        time.sleep(0.04)
    if last_good is None:
        return None, 0, 0
    h, w = int(last_good.shape[0]), int(last_good.shape[1])
    return last_good, w, h


def quick_warmup(cap, attempts: int = 5) -> bool:
    for _ in range(max(1, attempts)):
        try:
            ret, frame = cap.read()
            if ret and frame_ok(frame):
                return True
        except Exception as e:
            logger.debug("quick_warmup: %s", e)
        time.sleep(0.04)
    return False


def open_prepared_capture(
    index: int, preferred_w: int, preferred_h: int
) -> Tuple[object | None, int, int]:
    import cv2

    for w, h in _resolution_candidates(preferred_w, preferred_h):
        cap = open_video_capture(index)
        if cap is None or not cap.isOpened():
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
            continue
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            frame, fw, fh = _warmup_read_valid_frame(cap)
            if frame is None:
                cap.release()
                continue
            return cap, fw, fh
        except Exception as e:
            logger.warning("打开摄像头 %s @ %dx%d 失败: %s", index, w, h, e)
            try:
                cap.release()
            except Exception:
                pass
    return None, 0, 0


def probe_cameras(max_index: int = 4) -> List[Tuple[int, str]]:
    """探测可用摄像头；必须在主线程调用（cv2.VideoCapture 在 QThread 里会崩溃）。"""
    found: List[Tuple[int, str]] = []
    for i in range(int(max_index)):
        cap = open_video_capture(i)
        try:
            if not cap.isOpened():
                continue
            frame, fw, fh = _warmup_read_valid_frame(cap, attempts=8)
            if frame is None:
                continue
            found.append((i, f"摄像头 {i} ({fw}×{fh})"))
        except Exception as e:
            logger.debug("探测摄像头 %s 失败: %s", i, e)
        finally:
            try:
                cap.release()
            except Exception:
                pass
    return found
