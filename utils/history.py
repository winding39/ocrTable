"""OCR 任务历史记录 — data/history.json。"""
from __future__ import annotations

import json
import os
from datetime import datetime

import config as cfg

HISTORY_PATH = os.path.join(cfg.BASE_DIR, "data", "history.json")


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)


def load_records() -> list[dict]:
    _ensure_dir()
    if not os.path.isfile(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_record(record: dict) -> dict:
    """追加一条记录，返回带 id 的完整记录。"""
    records = load_records()
    rid = (max((r.get("id", 0) for r in records), default=0)) + 1
    full = {
        "id": rid,
        "created_at": record.get("created_at")
        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "photo_count": int(record.get("photo_count", 0)),
        "photo_names": list(record.get("photo_names") or []),
        "xlsx_path": record.get("xlsx_path") or "",
        "xlsx_name": record.get("xlsx_name")
        or (os.path.basename(record.get("xlsx_path", "")) if record.get("xlsx_path") else ""),
        "status": record.get("status") or "unknown",
        "message": record.get("message") or "",
        "task_id": record.get("task_id"),
    }
    records.insert(0, full)
    _save(records)
    return full


def clear_records() -> None:
    _save([])


def _save(records: list[dict]) -> None:
    _ensure_dir()
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
