"""应用配置：.env + data/app_settings.json"""
from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

VISION_API_URL = os.environ.get(
    "VISION_API_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
VISION_API_KEY = os.environ.get("VISION_API_KEY", "")
VISION_API_MODEL = os.environ.get("VISION_API_MODEL", "qwen-vl-ocr-latest")

_v_think = os.environ.get("VISION_ENABLE_THINKING", "0").strip().lower()
VISION_ENABLE_THINKING = _v_think not in ("0", "false", "no")

_v = os.environ.get("OCR_TWO_STAGE", "1").strip().lower()
OCR_TWO_STAGE = _v not in ("0", "false", "no")

TEXT_STRUCTURE_API_URL = os.environ.get("TEXT_STRUCTURE_API_URL", "").strip()
TEXT_STRUCTURE_API_KEY = os.environ.get("TEXT_STRUCTURE_API_KEY", "").strip()
TEXT_STRUCTURE_MODEL = (
    os.environ.get("TEXT_STRUCTURE_MODEL", "qwen-plus").strip() or "qwen-plus"
)

try:
    OCR_API_TIMEOUT = max(60, int(os.environ.get("OCR_API_TIMEOUT", "300")))
except ValueError:
    OCR_API_TIMEOUT = 300

try:
    OCR_MAX_TOKENS = max(1024, min(32768, int(os.environ.get("OCR_MAX_TOKENS", "16384"))))
except ValueError:
    OCR_MAX_TOKENS = 16384

FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "ocr_table_dev_secret")
try:
    FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
except ValueError:
    FLASK_PORT = 5000

IMAGES_DIR = os.path.join(BASE_DIR, "data", "images")
EXPORTS_DIR = os.path.join(BASE_DIR, "data", "exports")
SETTINGS_PATH = os.path.join(BASE_DIR, "data", "app_settings.json")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

DEFAULT_STAGE1_PROMPT = """你是表格 OCR 转写助手。请根据图片逐字转写所有印刷与手写文字，不要编造。

输出 Markdown：
### 表头
### 表格（表头与每一行明细，含所有手写列）
### 表尾

手写算式（如 885+329=1214、3k×4+1140）须完整保留。被划掉的内容请标注划掉线。"""

DEFAULT_STAGE2_PROMPT = """你是表格数据提取专家。根据下方 OCR 转写，识别表格所有列（含手写列），输出 JSON。

要求：
1. 自动识别表格有哪些列（印刷+手写都识别）；照片里有几列就输出几列，不要遗漏
2. 手写内容完整保留（算式保留原文；被划掉的部分只保留最终有效内容）
3. 每一行数据与表格行一一对应，空单元格用空字符串
4. 输出格式：{"headers": ["列1","列2",...], "rows": [["值","值",...], ...]}
仅输出 JSON，禁止任何解释、Markdown 或额外字符。"""

DEFAULT_SINGLE_PROMPT = """你是表格识别专家。请识别图片中的表格，自动识别所有列（印刷+手写），输出 JSON。

要求：
1. 照片里有几列就识别几列，不要遗漏手写列
2. 手写内容完整保留
3. 输出格式：{"headers": ["列1","列2",...], "rows": [["值","值",...], ...]}
仅输出 JSON，禁止任何解释、Markdown 或额外字符。"""


def load_app_settings() -> dict:
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_app_settings(data: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_stage1_prompt() -> str:
    s = load_app_settings()
    p = (s.get("stage1_prompt") or "").strip()
    return p or DEFAULT_STAGE1_PROMPT


def get_stage2_prompt() -> str:
    s = load_app_settings()
    p = (s.get("stage2_prompt") or "").strip()
    return p or DEFAULT_STAGE2_PROMPT


def get_single_prompt() -> str:
    s = load_app_settings()
    p = (s.get("single_prompt") or "").strip()
    return p or DEFAULT_SINGLE_PROMPT


def get_ocr_two_stage() -> bool:
    s = load_app_settings()
    if "ocr_two_stage" in s:
        return bool(s["ocr_two_stage"])
    return OCR_TWO_STAGE


def get_public_settings() -> dict:
    """返回可暴露给前端的设置（API Key 脱敏）。"""
    s = load_app_settings()
    key = s.get("vision_api_key") or VISION_API_KEY
    masked = ""
    if key:
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    return {
        "vision_api_url": s.get("vision_api_url") or VISION_API_URL,
        "vision_api_key_masked": masked,
        "vision_api_key_set": bool(key),
        "vision_api_model": s.get("vision_api_model") or VISION_API_MODEL,
        "text_structure_api_url": s.get("text_structure_api_url") or TEXT_STRUCTURE_API_URL,
        "text_structure_api_key_set": bool(
            s.get("text_structure_api_key") or TEXT_STRUCTURE_API_KEY
        ),
        "text_structure_model": s.get("text_structure_model") or TEXT_STRUCTURE_MODEL,
        "ocr_two_stage": get_ocr_two_stage(),
        "ocr_max_tokens": s.get("ocr_max_tokens") or OCR_MAX_TOKENS,
        "ocr_api_timeout": s.get("ocr_api_timeout") or OCR_API_TIMEOUT,
    }


def get_runtime_config() -> dict:
    """OCR 运行时使用的完整配置。"""
    s = load_app_settings()
    return {
        "vision_api_url": s.get("vision_api_url") or VISION_API_URL,
        "vision_api_key": s.get("vision_api_key") or VISION_API_KEY,
        "vision_api_model": s.get("vision_api_model") or VISION_API_MODEL,
        "text_structure_api_url": s.get("text_structure_api_url") or TEXT_STRUCTURE_API_URL,
        "text_structure_api_key": s.get("text_structure_api_key") or TEXT_STRUCTURE_API_KEY,
        "text_structure_model": s.get("text_structure_model") or TEXT_STRUCTURE_MODEL,
        "ocr_two_stage": get_ocr_two_stage(),
        "ocr_max_tokens": s.get("ocr_max_tokens") or OCR_MAX_TOKENS,
        "ocr_api_timeout": s.get("ocr_api_timeout") or OCR_API_TIMEOUT,
        "vision_enable_thinking": s.get("vision_enable_thinking", VISION_ENABLE_THINKING),
    }


def save_model_settings(payload: dict) -> None:
    s = load_app_settings()
    for key in (
        "vision_api_url",
        "vision_api_model",
        "text_structure_api_url",
        "text_structure_model",
        "ocr_max_tokens",
        "ocr_api_timeout",
    ):
        if key in payload and payload[key] is not None:
            s[key] = payload[key]
    if payload.get("vision_api_key"):
        s["vision_api_key"] = payload["vision_api_key"]
    if payload.get("text_structure_api_key"):
        s["text_structure_api_key"] = payload["text_structure_api_key"]
    if "ocr_two_stage" in payload:
        s["ocr_two_stage"] = bool(payload["ocr_two_stage"])
    save_app_settings(s)


def save_prompt_settings(payload: dict) -> None:
    s = load_app_settings()
    for key in ("stage1_prompt", "stage2_prompt", "single_prompt"):
        if key in payload:
            s[key] = payload[key]
    save_app_settings(s)


def write_env_from_settings() -> None:
    """将关键设置同步到 .env（可选）。"""
    s = load_app_settings()
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    mapping = {
        "VISION_API_URL": s.get("vision_api_url") or VISION_API_URL,
        "VISION_API_MODEL": s.get("vision_api_model") or VISION_API_MODEL,
        "TEXT_STRUCTURE_MODEL": s.get("text_structure_model") or TEXT_STRUCTURE_MODEL,
        "OCR_TWO_STAGE": "1" if get_ocr_two_stage() else "0",
    }
    if s.get("vision_api_key"):
        mapping["VISION_API_KEY"] = s["vision_api_key"]
    if s.get("text_structure_api_key"):
        mapping["TEXT_STRUCTURE_API_KEY"] = s["text_structure_api_key"]
    existing = {}
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            existing[k] = line
    out = []
    written = set()
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in mapping:
                out.append(f"{k}={mapping[k]}\n")
                written.add(k)
            else:
                out.append(line)
        else:
            out.append(line)
    for k, v in mapping.items():
        if k not in written:
            out.append(f"{k}={v}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(out)
